# R2 校准交接事故

` samples/releases.json` 中的 A 和 B 互相引用，B 的「校准」指向 C。R1 和 R2 均以 A、D 为入口，只有 C 从修订 `1` 的 10 换为修订 `2` 的 20。`samples/expected.json` 给出两版的手算明细和共享身份。

| 观察点 | 应有结果 | 故障表现 |
| --- | --- | --- |
| 按 R2 取包 | 交付 C 的修订 `2` 和载荷 20 | 交付 C 的修订 `1` 和载荷 10 |
| 源库关闭，依次装载并按发布号读取 | R1 读 10，R2 读 20，两版只共享 D | 两版都读 10，A、B、C、D 均共享 |
| 在已有旧版的隔离库装载独立构造的正确新版包 | 新版路径读 20，旧版路径仍读 10 | 新版路径仍读 10 |

从项目根运行端到端核账。

```sh
python3 -B -m unittest discover -s tests -p test_release_audit.py -k test_n7_binding_drift -v
```

核账将分别检查两版从入口沿「辅助」「校准」读到的载荷、可达明细和共享实例。故障断言 `WAREHOUSE_RELEASE_BINDING_DRIFT` 会显示实际值与预期值。原运行清单的 `verify` 运行完整回归，`demo` 用同一份校准样例展示离线装载、重开后的读值和实例号。