# regionCheck

电站系统使用的只读区划查询服务。先匹配2026整合版现名，无法完整匹配时查询历史地名和明确的官方撤设记录。服务不保存地址，不连接电站数据库，不调用地图或外部地址服务。

## 接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 就绪状态、版本、数据校验值 |
| GET | `/api/coverage` | 31省来源时点、补充公告、历史覆盖及限制 |
| GET | `/api/divisions/search?q=偃师市&limit=20` | 搜现名、历史名称、代码；limit为1—50 |
| GET | `/api/divisions/410307/history` | 查询关联撤设事件、年度快照、现行候选；支持6/9/12位代码 |
| POST | `/api/addresses/match` | 单条地址匹配 |
| POST | `/api/addresses/match-batch` | 批量地址匹配，保持输入顺序，最多100条 |
| GET | `/docs` | 无外部依赖的查询页面 |
| GET | `/openapi.json` | OpenAPI 3.1接口定义 |

单条请求：

```json
{"address":"河南省洛阳市偃师市大口镇董村"}
```

批量请求：

```json
{"addresses":["河南省洛阳市偃师市大口镇董村","朝阳区"]}
```

POST使用`Content-Type: application/json`，请求体上限256 KiB；每个地址2—1000字符。批次任一输入非法则整批返回400，不返回部分成功。

匹配响应的`candidates`包含现行`code`、`path`、`source`、`matched_level`、`match_method`、`evidence`、`unmatched_prefix`、`unparsed_suffix`和`suggested_address`。`related_events`返回匹配单位及其上级关联的明确历史事件，即使输入已是现名也会返回；例如现名“偃师区大口镇”仍能看到偃师市撤市设区记录。`evidence`只存本次名称转换采用的明确事件，包含事件年份、原码、承接码、原始理由和来源；未取得准确生效日时`effective_date=null`，不把补丁整理时间当作生效日。`history_complete=false`与`village_verified=false`在首版始终返回。

| status | 含义 | 系统处理建议 |
|---|---|---|
| matched | 现行区划唯一匹配至乡镇 | 使用候选区划字段；保留原地址 |
| historical | 通过明确的一对一撤设链唯一匹配至现行乡镇 | 使用候选及变更依据；保留原地址 |
| partial | 只匹配到部分层级，或残留未识别的乡镇名称 | 保留原文，补充或人工核查 |
| ambiguous | 存在多个现行候选 | 不自动选第一个 |
| needs_review | 地址冲突、历史关联未证实、多对一或拆分等情况 | 人工确认，`suggested_address=null` |
| unmatched | 未找到可用候选 | 保留原文，进入待处理队列 |

`automatic_conversion=true`仅表示`historical`结果具备唯一事件链，服务自身不修改任何电站记录。`suggested_address`只规范化已识别的省至乡路径，村、路、门牌仅保留原文字串，不能视为验证过的现势村级地址。NFKC及去空格后的输入另列`normalized_input`，原文保留在`input`。

错误响应形如`{"error":"..."}`；400表示参数或JSON非法，404表示代码或路由未找到，413表示体积超限，415表示Content-Type错误，503表示并发已满。请求日志不记录地址或搜索词。

## 历史边界

首版数据来自已经核验的2023基线及2026官方四级整合库：41989个现行节点，38769个乡级。当前构建包含2023、2026两期快照，以及原项目事件补丁提取的22条撤设记录。这不是1980年至今的完整变更档案。新增设立但没有撤设前身的补丁不形成地址转换边。

统计码与民政码的同码异名、异码同名不自动生成事件。历史快照名称可以检索；缺少明确承接证据时不能自动转换。N→1合并及1→N拆分返回人工确认；只有已明确关联且最终名称与现行记录一致的一对一链才允许转换。精确边界归属仍需地址或地块资料。

各省真实时点及补充公告随响应返回，不声明全国统一截至某一天。历史资料缺失不代表行政单位没有发生过变化。查询某代码的历史快照时，代码跨来源可能指向不同实体，不将它们拼成一条更名记录。

## 构建与测试

不需要安装Python第三方包，运行环境为Python 3.12。先按[官方数据重建文档](../../docs/2026-10-official-update.md)取得通过核验的`cache.db`，再生成独立只读发布数据：

```bash
python3 apps/region-check/build_data.py --database /path/cache.db --output /path/release-data
REGION_TEST_DATA=/path/release-data python3 -m unittest discover -s apps/region-check -p 'test_*.py' -v
python3 apps/region-check/server.py --data /path/release-data --host 127.0.0.1 --port 6130
```

构建要求新目录，校验31省当前节点数与父链，输出`regions.json`及SHA-256清单。启动再次核对哈希，错误则拒绝启动。原缓存、历史补丁和电站资料均不会被改写。生成数据不进Git，部署时作为独立发布包传输。

## 接入现有四服务架构

现有eplant的ui、ctrl、rum、data继续使用原有职责。regionCheck作为旁挂查询服务，加入`eplant_default`网络，由Rum通过`http://regionCheck:8000`调用；不建立第二套电站业务数据库或网关。

部署位置：`/root/infra/eplant/regionCheck`。容器名`regionCheck`，镜像`region-check:0.1.1`，宿主机绑定`127.0.0.1:6130`。这是内部接口，没有身份鉴权，不开放公网；如需外网访问，应经过系统现有鉴权入口。

```bash
# 在服务器部署目录内，先将构建好的发布数据放到data/
docker-compose build --pull=false
docker-compose up -d
curl --fail http://127.0.0.1:6130/health
curl --fail -H 'Content-Type: application/json' \
  -d '{"address":"河南省洛阳市偃师市大口镇董村"}' \
  http://127.0.0.1:6130/api/addresses/match
```

镜像使用主机缓存的`python:3.12-slim`，无运行期安装或外部下载。容器以非root身份运行，数据只读挂载，根文件系统只读，禁用额外能力，限制1 CPU/512 MiB/64进程；请求最多8个并发，连接超时10秒。日志轮转5 MiB×2。

本机查看页面可先建立SSH转发：`ssh -L 6130:127.0.0.1:6130 root@121.40.121.163`，再打开`http://127.0.0.1:6130/docs`。

更新时新建数据目录并校验SHA-256，备份旧发布文件与镜像标识，在独立compose项目中更新服务并重建容器，再核对健康检查与业务样本。不要在容器读取期间覆盖同一个数据文件。失败时恢复上版数据目录和镜像，仅重建regionCheck。首次发布撤销可在本目录执行`docker-compose down`，不删除其他服务、网络或数据卷。
