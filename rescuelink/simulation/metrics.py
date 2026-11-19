from collections import defaultdict
import math

def physical_metrics(attempts):
    decoded=[a for a in attempts if a["snr_linear"] is not None]
    bits=sum(a["coded_bits"] for a in decoded)
    info=sum(a["information_bits"] for a in decoded)
    duration=sum(a["duration"]+a["propagation"] for a in attempts)
    return dict(raw_ber=sum(a["raw_errors"] for a in decoded)/bits if bits else None,
                post_fec_ber=sum(a["post_errors"] for a in decoded)/info if info else None,
                fer=sum(not a["ok"] for a in attempts)/len(attempts) if attempts else 0,
                phy_header_failure_count=len(attempts)-len(decoded),
                snr_linear=sum(a["snr_linear"] for a in decoded)/len(decoded) if decoded else None,
                corrected_codewords=sum(a["corrected_codewords"] for a in attempts),
                detected_uncorrectable=sum(a["detected_uncorrectable"] for a in attempts),
                total_airtime=duration, coded_bits=bits, information_bits=info,
                # Successful frame bytes/airtime is a single-link diagnostic, distinct from app goodput.
                valid_frame_bps=sum(a["information_bits"] for a in attempts if a["ok"])/duration if duration else 0)

def shannon(bandwidth, snr_linear):
    return bandwidth*math.log2(1+snr_linear)

def network_metrics(net):
    s=net.summary()
    sos=[f.delivered-f.generated for f in net.flows.values() if f.app_type=="SOS_ALERT" and f.delivered is not None]
    images=[st for h in net.hosts.values() for st in h.images.values()]
    s.update(sos_latencies=sos, preview_times=[i["preview_time"] for i in images],
             image_full_times=[i["full_time"] for i in images],
             image_verified=sum(i["verified"] for i in images))
    s.update(physical_metrics(net.attempts))
    modes=defaultdict(float)
    for a in net.attempts: modes[a["mode"]]+=a["duration"]
    s["mode_airtime_seconds"]=dict(modes)
    residence={}
    for lane,c in net.controllers.items():
        changes=[e for e in net.events if e.kind=="mode_changed" and e.details["lane"]==lane]
        current=changes[0].details["old"] if changes else c.mode
        last=0
        totals=defaultdict(float)
        for e in changes:
            totals[current]+=e.time-last
            current,last=e.details["new"],e.time
        totals[current]+=max(0, s["simulated_seconds"]-last)
        residence[lane]=dict(totals)
    s["mode_residence_seconds"]=residence
    return s
