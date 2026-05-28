"""Inject YouTube transcript corpus into Renato Meirelles twin."""
import sqlite3, uuid, os, glob
from datetime import datetime, timezone

DB = 'rag/twins/twins.db'
PERSON_ID = 'renato-meirelles'

files = sorted(glob.glob('rag/twins/_t_*.txt'))
print(f"Found {len(files)} transcript files")

now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
conn = sqlite3.connect(DB)
cursor = conn.cursor()

injected = 0
for fp in files:
    basename = os.path.basename(fp)
    with open(fp) as f:
        content = f.read()
    
    lines = content.split('\n')
    title = lines[0].replace('# ', '')
    url = lines[1].replace('# URL: ', '') if len(lines) > 1 else ''
    text = '\n'.join(lines[2:]).strip()
    
    words = len(text.split())
    if words < 50:
        continue
    
    chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{PERSON_ID}-yt-{os.path.basename(fp)}"))
    
    cursor.execute("DELETE FROM corpus_chunk WHERE id=?", (chunk_id,))
    
    cursor.execute("""
        INSERT INTO corpus_chunk 
        (id, person_id, source_url, source_type, source_date, first_person, 
         text, token_count, quality_score, holdout, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
    """, (
        chunk_id, PERSON_ID, url, "video", "2024-10-07", 1,
        text, words, 1.0, now
    ))
    injected += 1
    print(f"  [{words}w] {title[:80]}")

conn.commit()

cursor.execute("""
    SELECT COUNT(*), ROUND(AVG(quality_score),4), ROUND(MIN(quality_score),4), SUM(token_count) 
    FROM corpus_chunk WHERE person_id=?
""", (PERSON_ID,))
count, avg, min_score, total_tokens = cursor.fetchone()
print(f"\nTotal: {count} chunks, {total_tokens} tokens, Avg quality: {avg}, Min: {min_score}")

conn.close()
