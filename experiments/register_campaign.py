"""Campaign registration script.

新しいキャンペーンを Experiment Manager に登録し、campaign_id を発行する。
同じキャンペーンを継続する場合は再実行不要。

Usage:
    python experiments/register_campaign.py

Requirements:
    Docker services must be running:
        docker compose up -d madsci_mongo event_manager experiment_manager

Output:
    campaign_id が表示される。
    experiments/ 内の対象スクリプトの CAMPAIGN_ID 定数にコピーして使う。
"""

from madsci.client.experiment_client import ExperimentClient
from madsci.common.types.experiment_types import ExperimentalCampaign

# ---------------------------------------------------------------------------
# キャンペーン情報 — 実行前にここを編集する
# ---------------------------------------------------------------------------

CAMPAIGN_NAME = "キャンペーン名をここに入力"
"""
例:
  "高粘度材料 キャリブレーション 2026 Q1"
  "放熱材グリス 最適配合探索 2026 Q2"
"""

CAMPAIGN_DESCRIPTION = """
キャンペーンの目的・概要をここに入力。

例:
  高粘度液体ディスペンサーの重力測定キャリブレーションを複数材料について実施し、
  Resource Manager に吐出パラメータを登録する。
"""

# ---------------------------------------------------------------------------
# Experiment Manager URL
# ---------------------------------------------------------------------------

EXPERIMENT_MANAGER_URL = "http://localhost:8002/"

# ---------------------------------------------------------------------------
# 登録処理
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ec = ExperimentClient(experiment_server_url=EXPERIMENT_MANAGER_URL)

    campaign = ec.register_campaign(
        ExperimentalCampaign(
            campaign_name=CAMPAIGN_NAME,
            campaign_description=CAMPAIGN_DESCRIPTION.strip(),
        )
    )

    campaign_id = campaign["campaign_id"]

    print("=" * 60)
    print("キャンペーン登録完了")
    print("=" * 60)
    print(f"  campaign_name : {CAMPAIGN_NAME}")
    print(f"  campaign_id   : {campaign_id}")
    print("=" * 60)
    print()
    print("以下を対象の experiments/*.py の先頭にコピーしてください:")
    print()
    print(f'  CAMPAIGN_ID = "{campaign_id}"')
    print()
    print("ExperimentDesign への設定例:")
    print()
    print("  from madsci.common.types.auth_types import OwnershipInfo")
    print()
    print("  experiment_design = ExperimentDesign(")
    print('      experiment_name="...",')
    print(f'      ownership_info=OwnershipInfo(campaign_id="{campaign_id}"),')
    print("  )")
