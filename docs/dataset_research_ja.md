# ポケモンチャンピオンズ向けバトルシミュレーション用データセット調査

## 結論（先に要点）
- **構築方法は確立可能**です。
- ただし、2026-04-25時点では「ポケモンチャンピオンズ」専用の公開API/全量データ配布は確認できないため、まずは以下の実運用可能な代替を採用します。
  1. **種族値・タイプ・特性一覧**: PokeAPI
  2. **特性効果（テキスト + 数式化トークン）**: PokeAPIの特性説明を正規化
  3. **主要技（採用率）・使用率上位ポケモン**: Smogon usage stats（gen9ou）

## データソース

### 1) 種族値/タイプ/特性（構造化）
- API: `https://pokeapi.co/api/v2/pokemon/{name}`
- ドキュメント: `https://pokeapi.co/docs/v2`
- 取得項目:
  - `stats`（hp/attack/defense/special-attack/special-defense/speed）
  - `types`
  - `abilities`

### 2) 特性効果（説明テキスト + 数式化）
- API: `https://pokeapi.co/api/v2/ability/{name}`
- 取得項目:
  - `effect_entries[].short_effect`（英語）
- 数式化方針:
  - 例: `30%` → `p=30/100`
  - 例: `1.5x` → `multiplier=1.5`
  - 例: `1/8` → `fraction=1/8`
  - 例: `+1 stage` → `stat_stage_change=+1`

### 3) 使用率上位ポケモン + 主要技
- Smogon usage:
  - 使用率: `https://www.smogon.com/stats/2026-03/gen9ou-0.txt`
  - 技採用率: `https://www.smogon.com/stats/2026-03/moveset/gen9ou-0.txt`
- 取得方針:
  - 使用率テーブル上位120体を抽出
  - 各ポケモンの moveset セクションから採用率上位10技（かつ採用率1%以上）を抽出

## ポケモンチャンピオンズへの適用時の注意
- 「チャンピオンズ」の公式ラダー統計が公開されたら、usage/moves をその公式統計に差し替えるのが最適。
- それまでは、ルール近似（6v6シングル、または目的の対戦形式）に近いSmogonフォーマットでブートストラップ可能。

## 実装
- スクリプト: `scripts/build_pokemon_dataset.py`
- 生成物:
  - `data/top120_pokemon_dataset_2026-03_gen9ou.json`
  - `data/top120_pokemon_dataset_2026-03_gen9ou.csv`

## 実行コマンド
```bash
python3 scripts/build_pokemon_dataset.py
```


## 補足: `python3 -m py_compile ...` で何も表示されない理由
- `py_compile` は**成功時に標準出力へ何も出さない**のが通常動作です。
- 失敗時だけエラー（SyntaxErrorなど）を表示します。
- 成功を明示したい場合は次のいずれかを使ってください。

```bash
python3 -m py_compile scripts/build_pokemon_dataset.py && echo "[OK] py_compile"
```

```bash
./scripts/run_checks.sh
```


## データセットが作成されない主な原因と今回の修正
- 原因1: 実行環境の外部HTTPS制限（`403 Forbidden`）で、Smogon/PokeAPIの取得に失敗すると処理が停止する。  
  - 修正: 取得失敗時のエラーメッセージを明確化し、原因URLとHTTP/Networkエラーが分かるようにしました。
- 原因2: 出力先ディレクトリ `data/` が存在しない環境では、書き込み時に失敗しうる。  
  - 修正: スクリプト側で出力ディレクトリを自動作成するようにしました（`--output-dir`対応）。

### 修正後の実行例
```bash
python3 scripts/build_pokemon_dataset.py --output-dir data --top-n 120
```
