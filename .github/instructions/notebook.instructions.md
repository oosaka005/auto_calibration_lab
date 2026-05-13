---
description: >
  Use when creating or editing Jupyter notebook files (notebooks/**/*.ipynb).
  Covers the role of notebooks in the MADSci project, MADSci client API usage,
  node action calls, resource manager access, and common import patterns for notebooks.
applyTo: "notebooks/**"
---

# Notebook Rules

## notebooks/ の役割

`notebooks/` は **人間が直接操作する作業用ファイル** を置く場所です。

MADSci では、Workflow/Action はスケジューラ（Workcell Manager）に自動実行させる手段ですが、
以下のような「自動化の外側にある作業」は Notebook で行います。

| 用途カテゴリ | 具体例 |
|---|---|
| **デバイス単体確認** | 実機への接続確認、コマンド単体テスト（dispense/suck_back など） |
| **Node Action 確認** | `RestNodeClient.send_action()` で Action を手動呼び出し、動作確認・デバッグ |
| **Resource Manager への登録・更新** | 材料情報（`attributes`）の初期登録、キャリブレーション結果の書き込み |
| **データ確認・可視化** | キャリブレーション結果グラフの表示など |

> **MADSci の設計方針との整合性**  
> MADSci 公式は「ノートブックは人間が介在する作業用インターフェース」として位置付けています。
> Resource Manager・Node の REST API はどちらも Python クライアントから直接叩けるため、
> Notebook はその自然な操作窓口になります。
> 自動化すべき処理は Workflow/Action に移行し、Notebook はセットアップ・検証・メンテナンス用途に限定するのが正しい使い方です。

### 既存ノートブックの役割

| ファイル | 役割 |
|---|---|
| `device_check.ipynb` | 天秤（BalanceProprietary）の実機コマンド確認 |
| `dispenser_check.ipynb` | ディスペンサー（HighViscosityDispenserProprietary）の実機確認・キャリブレーション実行 |
| `material_management.ipynb` | Resource Manager への材料情報の登録・更新・削除 |

---

## MADSci Client API (v0.7.0)

### NodeClient → RestNodeClient

`NodeClient` は廃止されました。ノードへのアクションを呼び出す場合は以下を使用してください。

```python
from madsci.client.node.rest_node_client import RestNodeClient
from madsci.common.types.action_types import ActionRequest

node_client = RestNodeClient(url="http://localhost:2000/")
```

**変更点まとめ:**

| 項目 | 旧（廃止） | 新（v0.7.0） |
|---|---|---|
| インポートパス | `madsci.client.node_client` | `madsci.client.node.rest_node_client` |
| クラス名 | `NodeClient` | `RestNodeClient` |
| コンストラクタ引数 | `node_url=URL` | `url=URL` |
| アクション呼び出し | `call_action(action_name=..., args=...)` | `send_action(ActionRequest(action_name=..., args=...))` |

---

### アクション呼び出しパターン

```python
from madsci.client.node.rest_node_client import RestNodeClient
from madsci.common.types.action_types import ActionRequest

node_client = RestNodeClient(url="http://localhost:2000/")

result = node_client.send_action(
    ActionRequest(
        action_name="action_name_here",
        args={
            "param1": value1,
            "param2": value2,
        },
    )
)
print(f"ステータス: {result.status}")
if result.json_result:
    import json
    print(json.dumps(result.json_result, indent=2, ensure_ascii=False))
```

---

### ResourceClient

ResourceClient のインポートパスは変わっていません。

```python
from madsci.client.resource_client import ResourceClient

resource_client = ResourceClient(resource_server_url="http://localhost:8003/")
```

---

## ノードポート

| ノード | ポート |
|---|---|
| `high_viscosity_liquid_weighing` | `2000` |
| Resource Manager | `8003` |

---

## デバイスの直接インポート

notebooks から `devices/` のクラスを直接インポートする場合は、`__init__.py` をスキップして直接ロードします（`DEVICE_REGISTRY` を介さないため）。

```python
import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(os.path.abspath(".."))

def import_device(filename: str):
    path = PROJECT_ROOT / "devices" / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
```
