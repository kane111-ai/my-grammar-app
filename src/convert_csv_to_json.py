import csv
import json
import os

def convert():
    # パスをこのファイルの場所基準に設定
    base_dir = os.path.dirname(__file__)
    csv_file_path = os.path.join(base_dir, '../data/questions.csv')
    json_file_path = os.path.join(base_dir, '../data/questions.json')

    if not os.path.exists(csv_file_path):
        print(f"エラー: {csv_file_path} が見つかりません。")
        return

    json_data = []

    with open(csv_file_path, encoding='utf-8-sig') as csv_file:
        csv_reader = csv.DictReader(csv_file)
        
        for row in csv_reader:
            try:
                question_item = {
                    "id": int(row['ID']),
                    "section": row['Section'],
                    "question": row['Question'],
                    "options": [
                        row['Option 1'],
                        row['Option 2'],
                        row['Option 3'],
                        row['Option 4']
                    ],
                    # スプレッドシートの 1-4 を プログラム用の 0-3 に変換
                    "answer": int(row['Ans(1-4)']) - 1 if row['Ans(1-4)'].isdigit() else 0,
                    "translation": row['Translation'],
                    "explanation": row['Explanation'],
                    # 忘却曲線用の初期ステータス
                    "interval": 0,
                    "ease": 2.5,
                    "next_review": 0
                }
                json_data.append(question_item)
            except KeyError as e:
                print(f"列名が一致しません: {e}")
                return

    with open(json_file_path, 'w', encoding='utf-8') as json_file:
        json.dump(json_data, json_file, ensure_ascii=False, indent=4)

    print(f"成功！ {len(json_data)} 問を JSON に変換しました。")

if __name__ == "__main__":
    convert()