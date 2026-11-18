# 环境监测校准发布库

环境监测资料组用这套工具把日批使用的校准口径交给隔离质控库。工具使用 Python 3.11 标准库和 SQLite，源库与隔离库分别持久化。所有路径均从项目根运行。

```sh
python3 -B verify.py
python3 -B demo.py
```

演示在临时目录创建两侧库，从 `samples/releases.json` 读取业务输入，用 `samples/expected.json` 的独立手算值核对实际输出。记录、发布包和入口都由公开接口生成。

## 一天的交接

1. 校准员登记 A、B、C、D。A 的「辅助」指向 B，B 的「回入口」指回 A，「校准」指向 C。
2. 校准员登记 C 的两份精确修订，来源刻度值分别是 10 和 20。两个修订同时可选。
3. 发布员分别固定 R1 和 R2 的选表，入口依次为 A、D。两版只更换 C 的修订。
4. 发布员按号取包。每版交付 A、B、C、D 及三条具名边。仅选入而不可达的记录留在源库。
5. 源库关闭后，隔离库校验并装载两包。A、B 随可达校准换版分离，D 的固定解释相同并共享编号。
6. 质控员从各版第一个入口依次沿「辅助」「校准」读取 10 和 20，核对入口和目标的实例编号。
7. 质控员从全部入口核账。循环和汇合只计一个实例，明细按逻辑键和编号排序。
8. 源端可追加更正。隔离库重开后，旧发布号仍返回原入口、原编号和原校准值。

## Python 接口

| 导入路径 | 调用和结果 |
| --- | --- |
| `catalog.storage` | `open_source(path)` 打开并初始化源库，同时准备发布目录。 |
| `catalog.revisions` | `put(db, key, revision, payload, references=())` 返回不可变 `SourceRevision`。引用可用映射或由两个元素组成的序列项。 |
| `releases.catalog` | `freeze(db, release_id, selection, entries)` 接受逻辑键到精确修订号的映射及有序入口序列，返回 `FrozenRelease`。 |
| `exchange.packages` | `pack(db, release_id)` 返回自足 `ReleasePackage`。 |
| `exchange.encoding` | `encode_package(package)` 返回规范 JSON 文本，`decode_package(text)` 解析结构并保留待语义校验的重复记录和边。 |
| `warehouse.storage` | `open_warehouse(path)` 打开并初始化隔离库，业务调用结束后由调用方关闭连接。 |
| `warehouse.imports` | `mount(db, package, before_commit=None)` 接受包对象、JSON 文本或 UTF-8 字节，返回有序 `(key, instance_id)` 元组。 |
| `audit.entrypoints` | `entries(db, release_id)` 返回已提交的有序 `(key, instance_id)` 元组。 |
| `audit.traversal` | `follow(db, release_id, position, path)` 从零基入口位置沿具名边序列读取 `BoundInstance`。 |
| `audit.inventory` | `inventory(db, release_id)` 返回 `Reconciliation`，其 `rows` 含键、修订、编号、原载荷，`count` 为去重条数。 |

标识为非空且可编码为 UTF-8 的字符串，按原值精确比较。载荷是 Python 整数，使用来源刻度，接受零和负值，拒绝缺省、空值、布尔及其他类型。引用、入口及路径都使用有限数据。空引用表示叶记录，空入口形成空图，空路径返回入口。入口序列允许重复逻辑键，每个位置各自保留。

线格式是一个包含 `release_id`、`entries`、`records` 的 JSON 对象。每条记录含 `key`、`revision`、`payload`、`references`。`payload` 是 JSON 整数，`references` 是 `[边名, 目标逻辑键]` 对的数组。目标键在同包内唯一解析。规范编码按逻辑键和边名排列，保留入口原顺序。同库内两个根的可达图若在逻辑键、精确修订、整数载荷和具名边上完全相同，则共享同一实例号。独立库分别分配编号。

非法字段、固定发布的缺失入口或引用、非法包及同号异内容报 `ValueError`。未知精确修订、未知发布和缺失路径边报 `KeyError`，入口位置越界报 `IndexError`。未知版本的取件和无效固定请求均无发布结果。重试已登记的同内容输入返回既有结果。包语义校验先于入仓业务写入。新装载的零参数 `before_commit` 在实例、边、回执全部准备好后运行，可抛出异常以触发回滚。钩子应由调用方用于观察或中止，不得操作连接事务或生命周期。钩子异常和 SQLite 装载错误作为 `warehouse.storage.MountError` 返回，原异常保留为原因。

可在空库或现有库上重复调用打开与初始化入口。样例录入是显式动作，使用 `put`、`freeze` 和 `mount` 的正常冲突语义。原回归覆盖同号冲突、缺失传递依赖、重复项、闭包边界、等价包重装、循环换版、倒序装载、提交前失败、用户数据保留和隔离重开。
