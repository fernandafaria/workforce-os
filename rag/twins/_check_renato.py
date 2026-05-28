import sqlite3
conn = sqlite3.connect('rag/twins/twins.db')
cursor = conn.cursor()

for table in ['person', 'corpus_chunk', 'twin']:
    cursor.execute(f"PRAGMA table_info({table})")
    cols = cursor.fetchall()
    print(f"\n{table}:")
    for c in cols:
        print(f"  {c[1]} ({c[2]})")
    cursor.execute(f"SELECT * FROM {table}")
    rows = cursor.fetchall()
    print(f"  ROWS: {len(rows)}")
    for r in rows[:1]:
        for i, v in enumerate(r):
            print(f"    {cols[i][1]}: {str(v)[:150]}")

conn.close()
