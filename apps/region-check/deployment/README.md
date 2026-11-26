# 地区服务平滑发布

稳定入口为 `http://regionCheck:8000`，宿主机只监听 `127.0.0.1:6130`。入口容器运行只读 Nginx；`regionCheck-blue` 和 `regionCheck-green` 分别挂载不可变参考数据。调用方不感知后端实例名称。

2026-10-26 生产已完成首次入口接入。当前 green 为 0.1.3，blue 保留 0.1.2。入口、账户和界面切换经过本次用户确认。首次接入与日常后端更新是不同操作；后续更新只替换未承载请求的后端，不重建入口。

## 首次安装

1. 从实际运行版本读取镜像 ID、数据摘要、网络、服务配置和恢复配置。配置完整内容只留在服务器。
2. 使用根目录 `docker-compose.yml`，设置其要求的镜像 ID、两个不可变数据目录及入口配置目录。不得用旧单实例配置覆盖现网。
3. 用 `install -d -m 755` 创建入口配置目录，用 `install -m 644` 放置 `nginx.conf` 和 `upstream.conf`。配置目录必须允许 UID 101 遍历；不能依赖调用进程的 umask。
4. 先启动 blue、green 两后端，核对健康中的版本、数据 SHA256 及关键地区范围。
5. 用入口镜像、同一网络、UID 101、只读根目录、`/tmp` 临时目录和**实际将挂载的配置目录**执行 `nginx -t -c /etc/nginx/region-check/nginx.conf`。不能用另一份权限不同的副本代替。
6. 首次替换原地区容器需要单独授权。只执行 `up -d --no-deps region-check`，不整体停机、不重启账户、数据或业务服务。

第一次生产接入曾因 umask 将配置目录创建为 0700 而失败，原地区服务已自动恢复。修正为 0755，并增加实际目录/实际 UID 检查后重试成功。首次迁移本身仍有短暂地区查询空窗；不能把后续平滑切换的测试结果用于声称首次安装没有中断。

## 日常更新

1. 读取 `upstream.conf` 确认当前实例。确认 `docker exec regionCheck ps -o args` 没有 `worker process is shutting down`；仍在处理旧请求时保留两个实例，等待完成。
2. 仅为非活动实例准备新镜像和全新数据目录。核对原数据摘要，不在使用中的目录覆盖文件。
3. 使用精确服务名启动非活动实例，保留活动实例和入口。核对行政记录、事件、父链、管理范围及数据摘要。
4. 先只验证切换计划，再按本次授权执行切换，例如：

```bash
python3 switch_backend.py --config-dir /absolute/router-config \
  --candidate regionCheck-blue --version 0.1.4 \
  --data-sha256 REVIEWED_DATA_SHA256 --image-id sha256:REVIEWED_IMAGE_ID
# 相同参数增加 --execute 才会修改路由并平滑 reload。
```

5. 脚本校验候选身份、当前路由、挂载、网络及未完成请求。配置写入使用原子替换，先 `nginx -t`，再平滑 reload，最后核对入口实际返回的版本和数据摘要。入口容器不重启；旧 worker 继续处理已经接收的请求。
6. 保留旧后端及数据，直到旧 worker 退出。`previous_requests_draining=true` 表示仍须等待，不能删除或重建旧实例。脚本不停止、删除或重建任何容器。

切换失败时脚本恢复原 upstream，并验证旧路由。需要恢复旧版本时，把保留的旧实例作为候选，使用其原始镜像 ID、版本和数据摘要执行同一流程。禁止恢复人员业务表。

本方案改善计划内后端升级，不等于多主机容灾。入口自身升级仍需单独评估；不要把替换入口镜像混进普通数据更新。

## 验证

```bash
REGION_TEST_DATA=/absolute/release-data python3 -m unittest discover -s apps/region-check -p 'test_*.py'
python3 apps/region-check/deployment/verify_blue_green.py
```

后者需要本机已有 `python:3.12-slim`、`nginx:1.27-alpine`，只创建带随机名称和任务标签的隔离网络及合成服务，结束后清理自身资源。验证连续请求、进行中请求、坏候选拒绝、反向切换和入口身份不变，不访问生产服务。2026-10-26 验证 1358 次连续请求，失败为 0。

Nginx 平滑 reload 行为依据：[官方进程控制文档](https://nginx.org/en/docs/control.html)。请求访问日志关闭，入口只转发原只读接口，不增加鉴权外网入口。
