# regionCheck

电站系统使用的只读区划查询服务。先匹配2026整合版现名，无法完整匹配时查询历史地名和明确的官方撤设记录。服务不保存地址，不连接电站数据库，不调用地图或外部地址服务。

## 接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 就绪状态、版本、数据校验值 |
| GET | `/api/coverage` | 31省来源时点、补充公告、历史覆盖及限制 |
| GET | `/api/divisions/tree` | 完整现行省／市／区县／乡镇目录；不含历史名称、不分页 |
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

`GET /api/divisions/tree`供地区选择器使用，只从发布包`target_year`的`active`节点及其完整父链生成，不合并历史快照、撤设前名称、搜索别名或业务数据中的地址。接口不接受查询参数，也没有搜索接口的50项限制。返回结构：

```json
{"data":[{"province":"福建省","cities":[{"city":"福州市","districts":["长乐区"],"towns":{"长乐区":["吴航街道"]},"direct_towns":[]}]}],"edition":"2026-10","target_year":2026,"data_sha256":"<发布包SHA-256>","current_only":true,"excluded_incomplete_paths":0}
```

示例仅展示结构，实际返回全国目录。各级按区划代码排序，同一父级下的名称去重；同名县、镇在不同父级下分别保留。直辖市和省直辖县级行政区划沿用发布包中的分组节点。父链缺失、层级错误或跨省错误时返回503，不退回历史目录，也不返回混合目录。已停用及其他年度节点不会进入结果。当前整合包的福州市目录包含13个县级节点，包含“长乐区”，不包含“长乐市”。

目录包含发布包全部41989个现行节点。其中102个地级直属乡镇的真实父链为省／市／乡镇，单列在所属城市的`direct_towns`中；`districts`始终只含真实县级名称，`towns`始终只含县下乡镇，不凭空增加区县。客户端可在同一选择列提供区县和直属乡镇，但必须保留类型；直属乡镇仍为level 4。使用四格路径保存范围的客户端可使用`省/市//乡镇`保留空缺的区县层级，不能把空格位删除后当作县级范围。同名区县与直属乡镇分别保留在各自字段中。旧客户端可忽略新增的`direct_towns`；兼容字段`excluded_incomplete_paths`现在为0。

完整现行父链名称串能够唯一精确匹配到乡镇时，匹配器优先采用该路径，避免将“中山市南区街道”中的跨词片段“市南区”误当成冲突县名。这个优先规则不处理简称、历史名称、额外前后缀或不完整路径；其他输入继续执行原有冲突与历史证据校验。响应路径中直属乡镇的层级序列为`[1,2,4]`、`matched_level=4`，消费端应按`level`映射省市区县乡镇，不能按数组下标猜层级。

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

错误响应形如`{"error":"..."}`；400表示参数或JSON非法，404表示代码或路由未找到，413表示体积超限，415表示Content-Type错误，503表示并发已满或现行目录无法提供有效完整父链。请求日志不记录地址或搜索词。

## 管理区域识别（0.1.3）

现行行政目录不混入新区、开发区、管委会等管理节点。`managed_areas.json`维护有来源依据的名称、上级锚点和真实管辖范围；构建时还从2023统计快照保留已退出民政现行视图的管理名称，标为`mapping_required`，不能据此认为已撤销或认定现行范围。

单条及批量地址响应新增`managed_areas`：`status`、`candidate_total`、`matches`和`catalog_edition`。唯一核定的范围使顶层`status=managed`；每个匹配项包含稳定`id`、原匹配名、`parent_path`、`scope_paths`、关系类型及官方来源。`scope_paths`只使用真实现行节点及父链，可以为多个县下镇街的并集，不创建虚构县码。指定区域内的一个镇街时仅保留该镇街；不识别的尾部地址不会被丢掉后升级为全区。

`mapping_required`是系统覆盖不足，不是人员填错；`partial`保留未识别尾部；`ambiguous`不选第一个。同名通称必须带足够上级，显式省市冲突不会通过。原行政`candidates`保留原语义，调用方不得把它当成管理范围。搜索响应单列`managed_areas`，普通行政树不增加这些条目。

本次核定高邮经济开发区→马棚街道、新蒲新区→5镇3街道、泉州台商投资区→4乡镇。漳州台商区旧材料称角美镇，而现行目录已为角美街道，未凭同名推定边界不变。其他历史名称的范围仍待核查。健康响应公开管理目录版本、数量、已核定数量及`managed_catalog_loaded`；发布必须同时更新代码和含管理关系的数据包，不能只换镜像。

2026-10-26台创园资料补充先完成本地候选，随后随美的地区映射数据更新上线。合肥先锋网2026-01-06材料及中国农村网2025-12-24材料确认庐江台创园托管10个村（社区）。目录增加来源、旧统计代码及“台创园管委会”别名，并合并同一园区的历史管理名称。园区不进入行政树。规划面积及县域辐射区不能代替行政托管边界。现有四级目录未核定村级精确范围，仍返回`mapping_required`及空`scope_paths`，不能将郭河镇、同大镇全域作为园区授权范围。

以已验证发布数据为基线增补关系，保留所有行政记录和历史事件：

```bash
python3 apps/region-check/build_data.py --base-release /path/verified-data --output /path/new-data
python3 apps/region-check/audit_managed_areas.py --data /path/new-data --output /path/audit.json
REGION_TEST_DATA=/path/new-data python3 -m unittest discover -s apps/region-check -p 'test_*.py' -v
```

基线哈希、父链、成员现势及来源均检查后才可使用输出；输出目录须为新目录。`audit_managed_areas.py`核对13条本批名单区域，并列出全国历史管理名称候选与尚未核定的范围；该扫描不声称覆盖全国全部现行管理区域。

## 历史边界

2026-10-26美的复核补充平顶山高新区完整管理范围：卫东区皇台街道与叶县遵化店镇。依据高新区2026年公开的乡镇国土空间总体规划及统计年鉴，保留两个镇街各自真实行政父链。54项回归通过，数据包已通过既有稳定入口在线生效；行政记录及历史事件保持。濮阳经济技术开发区现行管理范围仍未核定，继续返回系统映射待补，不按2023统计节点推断现行完整边界。

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

部署位置：`/root/infra/eplant/regionCheck`。2026-10-26已将`regionCheck`改为稳定内部入口，green后端为`region-check:0.1.3`，blue保留0.1.2。宿主机仍绑定`127.0.0.1:6130`，不开放公网；外部访问继续经过现有鉴权入口。实际镜像以运行容器的完整ID为准。

```bash
# 固定入口健康与只读地区查询；部署步骤见下方平滑发布文档。
curl --fail http://127.0.0.1:6130/health
curl --fail -H 'Content-Type: application/json' \
  -d '{"address":"河南省洛阳市偃师市大口镇董村"}' \
  http://127.0.0.1:6130/api/addresses/match
```

镜像使用主机缓存的`python:3.12-slim`，无运行期安装或外部下载。容器以非root身份运行，数据只读挂载，根文件系统只读，禁用额外能力，限制1 CPU/512 MiB/64进程；请求最多8个并发，连接超时10秒。日志轮转5 MiB×2。

本机查看页面可先建立SSH转发：`ssh -L 6130:127.0.0.1:6130 root@121.40.121.163`，再打开`http://127.0.0.1:6130/docs`。

日常更新先准备非活动后端和全新数据目录，校验后通过`switch_backend.py`平滑切换固定入口。旧实例继续处理在途请求并保留恢复，不重建入口或任何业务服务。首次安装和入口自身升级另行评估，不执行整体停机。配置、权限及恢复步骤见[平滑发布](deployment/README.md)。
