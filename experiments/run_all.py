"""Reproducible measurements. All physical samples traverse original cable.py."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rescuelink.config import Config, Mode
from rescuelink.physical.channel import PhysicalLink
from rescuelink.protocol.frame import Frame,Kind
from rescuelink.protocol.application import Message
from rescuelink.simulation.scenarios import level1
from rescuelink.network.engine import Network
from rescuelink.media.image_transfer import demo_image
from rescuelink.simulation.metrics import physical_metrics,network_metrics,shannon

def physical_sweep(quick):
    out=[]
    modes={"Uncoded":Mode("Uncoded",16,False),"Hamming":Mode("Hamming",16,True)}
    for scheme in ("BPSK","ASK","BFSK"):
        for mode in modes:
            for noise in (0,.3,.7,1.0,1.4):
                link=PhysicalLink(Config(noise=noise),123,"sweep")
                attempts=[]
                try:
                    rng=np.random.default_rng(456)
                    for i in range(4 if quick else 40):
                        frame=Frame(Kind.DATA,1,4,2,1,payload=rng.bytes(128))
                        a=link.transmit(frame.pack(),modes[mode],scheme)
                        attempts.append({k:v for k,v in a.items() if k not in ("raw","tx","rx")})
                    m=physical_metrics(attempts)
                    m["link_goodput_bps"]=sum(a["ok"] for a in attempts)*128*8/m["total_airtime"]
                    # Equivalent illustrative lowpass bandwidth; Cable itself is not bandlimited.
                    snr=m["snr_linear"]
                    out.append(dict(scheme=scheme,mode=mode,noise=noise,seed=123,frames=len(attempts),
                                    equivalent_bandwidth_hz=24000,
                                    shannon_reference_bps=shannon(24000,snr) if snr is not None else None,
                                    **m,attempts=attempts))
                finally: link.close()
    return out

def noise_network(quick,root):
    rows=[]
    for noise in (0,.3,.7,1.0,1.4):
        with Network(Config(noise=noise,policy="Fixed Fast",max_retries=4),root/"received") as n:
            for i in range(3 if quick else 12):
                n.send(1,4,Message("TEXT",str(i),{},b"channel"*32),at=i*2)
            n.run()
            rows.append(dict(noise=noise,**network_metrics(n)))
    return rows

def adaptive(quick,root):
    out=[]
    for seed in ([42,43] if quick else range(42,48)):
        for policy in ("Fixed Fast","Fixed Survival","Auto"):
            with Network(Config(noise=.12,policy=policy,seed=seed,window=4),root/"received") as n:
                # Identical exogenous arrivals and low -> high -> low noise schedule.
                for i,t in enumerate(range(0,72,3)):
                    n.send(1,4,Message("TEXT",f"adaptive-{i}",{},b"status"*32),at=float(t))
                n.schedule(12,n.set_noise,1.0)
                n.schedule(42,n.set_noise,.12)
                n.run()
                s=network_metrics(n)
                s["phases"]=[]
                for start,end in ((0,12),(12,42),(42,s["simulated_seconds"])):
                    delivered_bits=sum(e.details["body_bytes"]*8 for e in n.events
                        if e.kind=="application_received" and start<=e.time<end)
                    retries=sum(e.kind=="retransmission" and start<=e.time<end for e in n.events)
                    s["phases"].append(dict(start=start,end=end,delivered_body_bits=delivered_bits,
                        goodput_bps=delivered_bits/max(end-start,1e-9),retransmissions=retries))
                s.update(experiment="adaptive",seed=seed,policy=policy)
                n.export(root/f"adaptive_{seed}_{policy.replace(' ','_')}")
                out.append(s)
    return out

def scheduling(quick,root):
    out=[]
    for seed in ([42,43,44] if quick else range(42,52)):
        for policy in ("FIFO","Priority"):
            with Network(Config(seed=seed,noise=.12,window=12,scheduler=policy,downlink_slowdown=3),root/"received") as n:
                n.start_image(2,4,demo_image(),False)
                n.send(1,4,Message("TEXT","load",{},b"load"*600),at=8)
                for j,t in enumerate((12,18,24)):
                    n.send(3,4,Message("SOS_ALERT",f"sos-{j}",{},b"SOS"),0,at=t)
                n.run()
                s=network_metrics(n)
                s.update(experiment="scheduling",seed=seed,scheduler=policy,
                         sos_mean=float(np.mean(s["sos_latencies"])),
                         sos_p95=float(np.percentile(s["sos_latencies"],95)))
                n.export(root/f"scheduling_{seed}_{policy}")
                out.append(s)
    return out

def transport(quick,root):
    out=[]
    for protocol in ("Stop-and-Wait","GBN"):
        with Network(Config(noise=.12,transport=protocol,window=4,length=100000,attenuation=0),root/"received") as n:
            n.send(1,4,Message("TEXT","transport",{},b"x"*(2048 if quick else 8192)))
            n.run()
            s=network_metrics(n)
            s.update(experiment="transport",protocol=protocol)
            out.append(s)
    return out

def progressive(quick,root):
    out=[]
    for enabled in (False,True):
        with Network(Config(noise=.15),root/"received") as n:
            n.start_image(2,4,demo_image(),enabled)
            n.run()
            s=network_metrics(n)
            s.update(experiment="progressive",progressive=enabled)
            s["first_image_time"]=next((x for x in s["preview_times"] if x is not None),None) if enabled else s["image_full_times"][0]
            s["image_input_bytes"]=len(demo_image())
            s["preview_extra_bytes"]=next(iter(n.image_jobs.values()))["meta"]["preview_size"] if enabled else 0
            out.append(s)
    return out

def chart(path,xlabel,ylabel,series):
    fig,ax=plt.subplots(figsize=(7,4))
    for label,x,y in series: ax.plot(x,y,"o-",label=label)
    ax.set(xlabel=xlabel,ylabel=ylabel)
    ax.grid(alpha=.25); ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(path,dpi=160); plt.close(fig)

def run(quick=True,output="outputs/experiments"):
    root=Path(output); root.mkdir(parents=True,exist_ok=True)
    results={"generated_utc":datetime.now(timezone.utc).isoformat(),"quick":quick,
             "course_cable_sha256":hashlib.sha256(Path("cable.py").read_bytes()).hexdigest(),
             "e1":[level1(d,n) for d in (b"",b"Hello","中文救援".encode(),bytes(range(256)),b"long"*200) for n in (0,.25)]}
    for name,fn in [("physical",physical_sweep),("noise_network",noise_network),("adaptive",adaptive),("scheduling",scheduling),
                    ("transport",transport),("progressive",progressive)]:
        print("Running",name,flush=True)
        results[name]=fn(quick) if name=="physical" else fn(quick,root)
        (root/"results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    scalar=[]
    for name in ("physical","noise_network","adaptive","scheduling","transport","progressive"):
        for row in results[name]:
            scalar.append({**{k:v for k,v in row.items() if not isinstance(v,(dict,list))},"experiment":name})
    fields=sorted(set().union(*(r.keys() for r in scalar)))
    with (root/"results.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(scalar)
    physical=results["physical"]
    def lines(metric,modes=("Uncoded",),schemes=("BPSK","ASK","BFSK")):
        return [(f"{s}/{m}",[r["noise"] for r in physical if r["mode"]==m and r["scheme"]==s],
                 [r[metric] for r in physical if r["mode"]==m and r["scheme"]==s]) for s in schemes for m in modes]
    ref=[r for r in physical if r["mode"]=="Uncoded" and r["scheme"]=="BPSK"]
    chart(root/"e2_shannon.png","Noise standard deviation","bit/s (different theoretical/operational meanings)",
          [("Shannon reference (24 kHz)",[r["noise"] for r in ref],[r["shannon_reference_bps"] for r in ref]),
           ("Star network application goodput",[r["noise"] for r in results["noise_network"]],[r["goodput_bps"] for r in results["noise_network"]])])
    chart(root/"e3_modulations.png","Noise standard deviation","Raw BER (payload, before FEC)",lines("raw_ber"))
    chart(root/"e4_coding.png","Noise standard deviation","Frame error rate",lines("fer",modes=("Uncoded","Hamming"),schemes=("BPSK",)))
    chart(root/"e4_goodput.png","Noise standard deviation","Single-link delivered payload bit/s",lines("link_goodput_bps",modes=("Uncoded","Hamming"),schemes=("BPSK",)))
    for group,field,metric,label in [("adaptive","policy","goodput_bps","Application goodput (bit/s)"),
                                     ("scheduling","scheduler","sos_mean","SOS application latency (s)"),
                                     ("transport","protocol","goodput_bps","Application goodput (bit/s)")]:
        rows=results[group]; names=list(dict.fromkeys(r[field] for r in rows))
        fig,ax=plt.subplots(figsize=(7,4)); means=[float(np.mean([r[metric] for r in rows if r[field]==name])) for name in names]
        ax.bar(names,means,color=["#e66b57","#3b9b9a","#e2af4b"][:len(names)])
        ax.set_ylabel(label); fig.tight_layout(); fig.savefig(root/f"{group}.png",dpi=160); plt.close(fig)
    print(json.dumps({"path":str((root/"results.json").resolve()),"rows":len(scalar)},indent=2))
    return results

if __name__=="__main__":
    p=argparse.ArgumentParser(); g=p.add_mutually_exclusive_group()
    g.add_argument("--quick",action="store_true"); g.add_argument("--full",action="store_true")
    p.add_argument("--output",default="outputs/experiments")
    args=p.parse_args(); run(not args.full,args.output)
