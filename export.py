#!/usr/bin/env python3
"""将所有数据集的 profile + 题目合并为一个 JSON 文件，供外部网页使用"""
import json
import os
import glob

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    data_dir = os.path.join(SCRIPT_DIR, 'data')
    output_file = os.path.join(SCRIPT_DIR, 'baziqia_all.json')

    all_persons = []
    for filepath in sorted(glob.glob(os.path.join(data_dir, '*.json'))):
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        metadata = data[0]
        contest_id = metadata.get('contest_id', os.path.basename(filepath).replace('.json', ''))
        year = metadata.get('current_year', '')

        for person in data[1:]:
            profile = person['profile']
            birth = profile['birth']
            entry = {
                'contest': contest_id,
                'year': year,
                'person_id': person['person_id'],
                'name': person.get('name', ''),
                'gender': profile['gender'],
                'birth': {
                    'year': birth['year'],
                    'month': birth['month'],
                    'day': birth['day'],
                    'hour': birth['hour'],
                    'minute': birth.get('minute', 0),
                },
                'questions': [
                    {
                        'question': q['question'],
                        'options': q['options'],
                        'answer': q['answer'],
                    }
                    for q in person['questions']
                ],
            }
            all_persons.append(entry)

    result = {
        'total_persons': len(all_persons),
        'total_questions': sum(len(p['questions']) for p in all_persons),
        'persons': all_persons,
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"已导出 {result['total_persons']} 个命主，{result['total_questions']} 道题目")
    print(f"输出文件: {output_file}")


if __name__ == '__main__':
    main()
