import sqlite3
conn = sqlite3.connect('rag/twins/twins.db')
conn.execute("DELETE FROM corpus_chunk WHERE person_id='renato-meirelles'")
conn.execute("DELETE FROM twin WHERE person_id='renato-meirelles'")
conn.execute("DELETE FROM person WHERE id='renato-meirelles'")
conn.commit()
conn.close()
print('Old twin cleared')
