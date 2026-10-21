# 2026年10月官方数据更新

本批于2026-10-20至2026-10-21整理，沿用原有 `patches/<年份>/*.json` 协议。仓库及 master 均指 `wenlei/china-administrative-division`。目标分区为2026，基线为2023；保留旧年度补丁，不新增第二套区划库。

本次继续核查此前20省的时点缺口：**16省已换入2026年官方完整名录，剩余4省逐省说明如下**。31省均有来源，29省使用省厅表、2省保留民政部接口归档；其中27省来源有2026时点，天津、上海、山东、广西仍未消除时点或原件获取缺口。

不同省份有不同截止日期，不能将其称为全国2026年10月同一时点现势库。`all_provinces_included=true`，`complete_national=false`。村级冻结于2023年。

## 其余20省逐省复核

| 省级地区 | 本次结果 | 官方时点 | 当前乡级数 | 依据及限制 |
|---|---|---|---:|---|
| 天津市 | 日期未声明 | 未声明 | 252 | [官方来源](https://mz.tj.gov.cn/BMFW1537/wyc/xzqhxxcx/202304/t20230425_6215701.html)；7月31日页面已发布；252条附件无截止日，不能把发布日期当数据日期。 |
| 河北省 | 已更新 | 2026-06-30 | 2254 | [官方来源](https://minzheng.hebei.gov.cn/detail?id=1051398)；44页PDF，2254条；保留赵家蓬区公所及柳树𨟠镇。 |
| 山西省 | 已更新 | 2026-06-30 | 1283 | [官方来源](https://mzt.shanxi.gov.cn/tzgg/202607/t20260714_10176760.html)；37页PDF，1283条；宋𦙶乡一处字形缺失按上期同码官方Excel保留，见下文。 |
| 内蒙古自治区 | 已更新 | 2026-06-30 | 1033 | [官方来源](https://mzt.nmg.gov.cn/zwgk/gsga/qhdm/202607/t20260717_2929989.html)；HTML全表1033条，按6月底版本核验。 |
| 上海市 | 日期未声明 | 未声明 | 218 | [官方来源](https://mzj.sh.gov.cn/MZ_zhuzhan1539_0-2-8-1459/20260727/535996b5abd045baac0c65552f4527d9.html)；7月27日完整表已纳入；218条正文未注明截止日，属于时点证据缺口。 |
| 安徽省 | 已更新 | 2026-06-30 | 1531 | [官方来源](https://mz.ah.gov.cn/public/21761/123433761.html)；Excel1531条，比旧版净增9；新增17码、退出本期8码。 |
| 江西省 | 已更新 | 2026-06-30 | 1581 | [官方来源](https://mzt.jiangxi.gov.cn/jxsmzt/col/col34862/content/content_2072245187928301568.html)；HTML1581条；360982108名称首字为官网错误图片，保留上期官方拆字写法。 |
| 山东省 | 原件获取受限 | 未声明 | 1826 | [官方来源](https://dmfw.mca.gov.cn/9095/xzqh/getList?code=370000&maxLevel=2)；有8月3日省厅发布及7月31日整表的媒体转载线索；官网证书/访问异常，原件未取得核验。保留未注明版本接口，不声称未发布。 |
| 河南省 | 已更新 | 2026-06-30 | 2474 | [官方来源](https://mzt.henan.gov.cn/2026/07-27/3379457.html)；Excel2474条，比旧版新增3个街道。 |
| 湖北省 | 已更新 | 2026-06-30 | 1260 | [官方来源](https://mzt.hubei.gov.cn/fbjd/zcwj/zcfg/202607/t20260715_5976683.shtml)；Excel1260条，原件明确截至6月30日。 |
| 湖南省 | 已更新 | 2026-06-30 | 1953 | [官方来源](https://mzt.hunan.gov.cn/mzt/xxgk/tjsj/202608/t20260803_34038652.html)；6月底全量1947条；另保留10月14日6个街道公告，合计1953条。 |
| 广东省 | 已更新 | 2026-06-30 | 1607 | [官方来源](https://smzt.gd.gov.cn/attachment/0/619/619623/4924190.pdf)；49页PDF1607条；末页明确6月30日，且说明个别已获批变更的代码尚未更新。保留本期实际公布值。 |
| 广西壮族自治区 | 原件获取受限 | 未声明 | 1257 | [官方来源](https://dmfw.mca.gov.cn/9095/xzqh/getList?code=450000&maxLevel=2)；省厅TLS握手失败，浏览器与网页工具均未取到2026全量代码原件；政府门户的2025年底数量介绍不能代替代码明细。无法断言未发布。 |
| 海南省 | 已更新 | 2026-06-30 | 218 | [官方来源](https://mz.hainan.gov.cn/smzt/0400/202607/be92e00817b64a26bd250988056f4434.shtml)；上半年版Excel218条；版名对应上半年期末，并非将7月31日发布日期作为截止日。 |
| 重庆市 | 已更新 | 2026-06-30 | 1028 | [官方来源](https://mzj.cq.gov.cn/zwgk_218/zfxxgkml/tzgg/202607/t20260710_15816287.html)；6月全表1028条；另合入9月1日4组编制/废止代码公告，条数不变。 |
| 四川省 | 已更新 | 2026-06-30 | 3101 | [官方来源](https://mzt.sc.gov.cn/scmzt/quhuaxinxi/2026/7/24/3e9fade9afb548958c2387ed44b5f29a.shtml)；112张原图3101条，逐页完整覆盖；与接口4组同名异码以省厅期次表为准，不能据此推断变更发生日期。 |
| 贵州省 | 已更新 | 2026-06-30 | 1513 | [官方来源](https://mzt.guizhou.gov.cn/xxgk/xxgkml/zdlyxx1/qhdm_88523/202607/t20260723_90652299.html)；HTML全表1513条，标题明确6月30日。 |
| 甘肃省 | 已更新 | 2026-06-30 | 1356 | [官方来源](https://mzt.gansu.gov.cn/mzt/c107824/202607/174359734.shtml)；Excel1356条，更新5组撤乡设镇代码。 |
| 宁夏回族自治区 | 已更新 | 2026-06-30 | 243 | [官方来源](https://mca.nx.gov.cn/xwzx/tzgg/202607/t20260706_5282444.html)；7页PDF243条，纳入田老庄镇640324107，旧乡码退出本期。 |
| 新疆维吾尔自治区 | 已更新 | 2026-06-30 | 1205 | [官方来源](https://mzt.xinjiang.gov.cn/xjmzt/c112990/202607/d4e25e9ed58e4371a1798d6e623ffc3d.shtml)；67张原图1205条，含省直辖县级市。原表外接口节点退出2026视图，历史保留。 |

山东另有[德州广播电视台转载线索](https://iapp.dztv.tv/share/YS0xNzktNDQ1Njk4NTQ.html)及[媒体完整表转载](https://sd.ifeng.com/c/8vJrfOdiy54)，表述为已检索到发布线索、原件获取受限，未将转载当作已核验省厅原件。广西未搜索到可核验2026原件，不等于官方未发布。

## 全国31省覆盖

| 省级地区 | 官方时点 | 当前有效乡级数 | 来源 |
|---|---|---:|---|
| 北京市 | 2026-06-30 | 343 | [省厅名录](https://mzj.beijing.gov.cn/art/2026/7/16/art_9984_692516.html) |
| 天津市 | 未声明 | 252 | [省厅名录](https://mz.tj.gov.cn/BMFW1537/wyc/xzqhxxcx/202304/t20230425_6215701.html) |
| 河北省 | 2026-06-30 | 2254 | [省厅名录](https://minzheng.hebei.gov.cn/detail?id=1051398) |
| 山西省 | 2026-06-30 | 1283 | [省厅名录](https://mzt.shanxi.gov.cn/tzgg/202607/t20260714_10176760.html) |
| 内蒙古自治区 | 2026-06-30 | 1033 | [省厅名录](https://mzt.nmg.gov.cn/zwgk/gsga/qhdm/202607/t20260717_2929989.html) |
| 辽宁省 | 2026-06-30 | 1354 | [省厅名录](https://mzt.ln.gov.cn/mzt/zfxxgk/fdzdgknr/lzyj/mztgfxwj/gggs/2026063015091795886/) |
| 吉林省 | 2026-07-28 | 972 | [省厅名录](https://mzt.jl.gov.cn/mztyw_74291/qhdm/fgwj/202607/t20260728_9671500.html) |
| 黑龙江省 | 2026-06-30 | 1314 | [省厅名录](https://mzt.hlj.gov.cn/mzt/c109882/202601/c00_31908649.shtml) |
| 上海市 | 未声明 | 218 | [省厅名录](https://mzj.sh.gov.cn/MZ_zhuzhan1539_0-2-8-1459/20260727/535996b5abd045baac0c65552f4527d9.html) |
| 江苏省 | 2026-06-30 | 1237 | [省厅名录](https://mzt.jiangsu.gov.cn/art/2026/7/2/art_78635_11723214.html) |
| 浙江省 | 2026-06-30 | 1365 | [省厅名录](https://mzt.zj.gov.cn/col/col1632784/art/2026/art_2305ba7c1c1d4ee99f89f2d3ae1b10a7.html) |
| 安徽省 | 2026-06-30 | 1531 | [省厅名录](https://mz.ah.gov.cn/public/21761/123433761.html) |
| 福建省 | 2026-06-30 | 1109 | [省厅名录](https://mzt.fujian.gov.cn/gk/tzgg/202607/t20260710_7176497.htm) |
| 江西省 | 2026-06-30 | 1581 | [省厅名录](https://mzt.jiangxi.gov.cn/jxsmzt/col/col34862/content/content_2072245187928301568.html) |
| 山东省 | 未声明 | 1826 | [民政部接口归档](https://dmfw.mca.gov.cn/9095/xzqh/getList?code=370000&maxLevel=2) |
| 河南省 | 2026-06-30 | 2474 | [省厅名录](https://mzt.henan.gov.cn/2026/07-27/3379457.html) |
| 湖北省 | 2026-06-30 | 1260 | [省厅名录](https://mzt.hubei.gov.cn/fbjd/zcwj/zcfg/202607/t20260715_5976683.shtml) |
| 湖南省 | 2026-06-30 | 1953 | [省厅名录](https://mzt.hunan.gov.cn/mzt/xxgk/tjsj/202608/t20260803_34038652.html) |
| 广东省 | 2026-06-30 | 1607 | [省厅名录](https://smzt.gd.gov.cn/attachment/0/619/619623/4924190.pdf) |
| 广西壮族自治区 | 未声明 | 1257 | [民政部接口归档](https://dmfw.mca.gov.cn/9095/xzqh/getList?code=450000&maxLevel=2) |
| 海南省 | 2026-06-30 | 218 | [省厅名录](https://mz.hainan.gov.cn/smzt/0400/202607/be92e00817b64a26bd250988056f4434.shtml) |
| 重庆市 | 2026-06-30 | 1028 | [省厅名录](https://mzj.cq.gov.cn/zwgk_218/zfxxgkml/tzgg/202607/t20260710_15816287.html) |
| 四川省 | 2026-06-30 | 3101 | [省厅名录](https://mzt.sc.gov.cn/scmzt/quhuaxinxi/2026/7/24/3e9fade9afb548958c2387ed44b5f29a.shtml) |
| 贵州省 | 2026-06-30 | 1513 | [省厅名录](https://mzt.guizhou.gov.cn/xxgk/xxgkml/zdlyxx1/qhdm_88523/202607/t20260723_90652299.html) |
| 云南省 | 2026-08-31 | 1429 | [省厅名录](https://ynmz.yn.gov.cn/bmfw/xzqh/qhdm/) |
| 西藏自治区 | 2026-06-30 | 731 | [省厅名录](https://mzt.xizang.gov.cn/zxzx/tzgg/202607/t20260729_551733.html) |
| 陕西省 | 2026-07-31 | 1317 | [省厅名录](https://mzt.shaanxi.gov.cn/bs/bmcx/201711/t20171107_2703806.html) |
| 甘肃省 | 2026-06-30 | 1356 | [省厅名录](https://mzt.gansu.gov.cn/mzt/c107824/202607/174359734.shtml) |
| 青海省 | 2026-07-31 | 405 | [省厅名录](https://mzt.qinghai.gov.cn/html/show-13599.html) |
| 宁夏回族自治区 | 2026-06-30 | 243 | [省厅名录](https://mca.nx.gov.cn/xwzx/tzgg/202607/t20260706_5282444.html) |
| 新疆维吾尔自治区 | 2026-06-30 | 1205 | [省厅名录](https://mzt.xinjiang.gov.cn/xjmzt/c112990/202607/d4e25e9ed58e4371a1798d6e623ffc3d.shtml) |

当前有效四级节点 **41989** 个，其中乡级 **38769** 个。这是所选来源的混合时点整合数，不作为全国2026年10月官方统计总数。

## 本次数据变化与例外

- 相对本 fork 合入前的 master（1886fc8）有效四级视图：新增44码、退出本期103码、同码字段变化0条。详见 [差异明细](../updates/2026-10-followup.diff.json)。退出本期视图不等同于行政实体撤销；旧码标记deprecated，历史补丁保留。
- 新疆：纠正上一版报告将机器成功识别的1170条误作表总数的结论。67页原表连续序号为1—1205，含省直辖县级市。替换此前1280条未声明版本的接口快照；本期3个原表新增码和78个接口表外节点逐项列于差异明细。不得将两组数据的差额解释为本年撤销数量。
- 四川：原图连续序号1—3101；省厅表中的大坪乡、贺波洛乡、鲁基乡、峨曲古乡与接口对应镇码存在期次差异，按省厅截至6月底的明确期次表保留，并记录差异。接口无截止日，不能据此重写省厅表或推断变更日期。
- 广东：原件明确部分乡级变更虽已获批，代码尚未更新；按本期公布代码，不推算或拼接新码。9处PDF稀有字缺失按原图与同码民政部文本校对恢复，规则按代码精确匹配。
- 山西140781201：本期PDF第20页显示“宋 乡”，采用上期省厅Excel同码“宋𦙶乡”。江西360982108：2026网页首字为errorImg.png，采用上期省厅“（门+合）山镇”。两处均不是本期无损提取，恢复规则、参考URL、参考截止日和原件SHA-256见来源清单name_restorations；未将缺字当作正式更名。
- 河北柳树𨟠镇、浙江干𬒗镇保留精确缺字恢复；青海大柴旦行委无独立县码的两个镇直接挂海西州，不伪造县级实体。
- 省直辖县级市和直辖市使用原库兼容中间节点；六位/九位码尾补零为十二位，不改变官方码值。

## 图片表的审查与完整性

四川112张、新疆67张官方原图均已本地归档。代码按整图与放大代码列提取，确保唯一代码、连续行序和全部页覆盖。名称经两种识别方式及民政部同码文本交叉核对；不一致、新码及上级名称识别缺失逐图复核。接口仅作校对，不补入省厅表未列节点。

- [四川逐行审查](../updates/2026-10-51-image-review.json)及[原图URL与SHA-256](../updates/2026-10-51-images.json)。
- [新疆逐行审查](../updates/2026-10-65-image-review.json)及[原图URL与SHA-256](../updates/2026-10-65-images.json)。
- 导入同时核验发布页、审查输入、原图清单和每张原图哈希；漏页、断序、重码、未经审查条目、未声明的新名称均拒绝导入。

## 重建与核验

直接使用已入库补丁不依赖重新下载官网。顺序以updates/2026-10.sources.json为准：先重放2024、2025事件及原2026.merged.json，再应用31省完整校准表，最后应用湖南10月及重庆9月增量。不得无序扫描补丁，也不能只应用2026.merged.json。

```bash
pnpm install --frozen-lockfile
pnpm --filter @cndiv/cli build
node packages/cli/dist/cli.js hydrate --year=2023 --cache=/path/baseline
node scripts/materialize-official-update.mjs \
  --baseline=/path/baseline/cache.db \
  --sources=updates/2026-10.sources.json \
  --output=/path/new-october-output
```

必须从2023基线重新重放，不能将本批补丁直接追加到上版已生成的2026库。输出目录必须不存在。脚本在补丁协议、有效父链、31省数量、基线逐字段比较、补丁审计数及SQLite完整性均通过后发布cache.db、coverage.json、replay.log。保留输入库除2026以外的全部年度；本次实际对2023基线完成逐字段不变验证，旧年度补丁未修改。`--require-complete`仍因4省时点/原件缺口拒绝构建，且不发布半成品。

从原件重新生成：按来源清单下载原件至raw/2026-10；青海DOC先用textutil -convert txt转为63-attachment-0.txt，湖南代码PDF用pdftotext -layout转为43-new.txt。河北、山西、广东、宁夏本期PDF分别保存为13/14/44/64-2026.pdf；旧浙江PDF及青海DOC仍沿用原名。四川、新疆将已提交的image-review.json及images.json分别复制为清单file及image_manifest所指定的原料名，并按原图清单下载全部图片，不重新采信未审查OCR。山西、江西缺字恢复需要同时归档清单所列上期官方参考原件。

```bash
python3 scripts/extract-official-gap-tables.py --raw raw/2026-10
python3 scripts/build-official-update.py \
  --sources updates/2026-10.sources.json --raw raw/2026-10 \
  --baseline /path/baseline/cache.db --output patches/2026
python3 scripts/verify-official-update.py \
  --sources updates/2026-10.sources.json --raw raw/2026-10 \
  --database /path/new-october-output/cache.db
python3 -m unittest discover -s scripts -p test_official_update.py
node scripts/validate-patches.mjs
```

原CLI导出可能包含deprecated及冻结村级；四级有效视图筛选year=2026 AND level<=4 AND status=active，必须附带coverage.json。原始大文件与数据库按仓库约定留在raw或本地输出，不提交Git。

## 验证结果

31省全部代码、名称、层级、父级及有效集合与来源清单、显式缺字恢复及两省增量投影逐字段一致；江苏1346、福建1203个四级节点与此前独立核验结果一致。Python回归15项通过；JavaScript测试240项通过、2项跳过；41份补丁协议检查通过，结构检查0错误，2项既有历史基线告警。本批补丁无结构告警。

本次不消除4省缺口，不将未声明版本接口、采集日期或发布日期标成2026截止日。
