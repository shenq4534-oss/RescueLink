# 两人协作

建议仓库名 `RescueLink`，默认 Private。不要把虚拟环境、凭据、个人照片和接收文件放进 Git；原创示例与实测图可以版本管理。老师原版 Cable 保留来源与 hash。

|负责人|边界|共同验收|
|---|---|---|
|同学一|physical/、protocol/、E1–E4、协议文档|物理测试、可靠性边界|
|同学二|network/、media/、app.py、E5–E7|三个创新、UI展示|
|两人|实验解释、PPT、报告|全套pytest、三个CLI、quick实验|

分支示例：`feature/physical`、`feature/emergency-ui`；PR 写清触发条件、结果与运行过的测试。CI 在 push/PR 后执行 pytest（包含原版物理链路和AppTest）。本机通过不等于远程 CI 已运行。

已有远程仓库后：

```powershell
git remote add origin https://github.com/YOUR_ACCOUNT/RescueLink.git
git push -u origin main
```

或在已安装并登录 GitHub CLI 的机器：

```powershell
gh repo create RescueLink --private --source . --remote origin --push
```

在 GitHub 仓库 Settings → Collaborators 邀请搭档账号。邀请会授予访问权限，应由仓库所有者确认具体账号后执行。本工程没有擅自邀请未知账号。
