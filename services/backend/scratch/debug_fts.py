import asyncio, re, sys
sys.path.append('.')
sys.stdout.reconfigure(encoding='utf-8')
from sqlalchemy import text, select
from app.core.database import async_session_maker
from app.intelligence.models import ProjectDocumentChunk

query = 'CSVインポート時のキー項目と、画面上で修正可能な項目について仕様を教えてください。'
# Extract alphanumeric keywords (e.g. CSV, API, PDF)
alpha_words = [w for w in re.findall(r"[A-Za-z0-9_]{2,}", query)]
# Extract Katakana keywords (e.g. インポート, キー)
katakana_words = [w for w in re.findall(r"[\u30A0-\u30FF]{2,}", query)]
# Extract Kanji keywords (e.g. 項目, 画面, 修正, 仕様)
kanji_words = [w for w in re.findall(r"[\u4E00-\u9FAF]{2,}", query)]
# Extract Vietnamese / Latin accented words
latin_words = [w for w in re.findall(r"[A-Za-z\u00C0-\u024F\u1EA0-\u1EF9]{2,}", query) if w not in alpha_words]

all_tokens = list(dict.fromkeys(alpha_words + katakana_words + kanji_words + latin_words))
print('all_tokens:', all_tokens)
clean_fts_words = [f'"{w}"*' for w in all_tokens[:10] if len(w) >= 2]
fts_match_query = ' OR '.join(clean_fts_words)
print('fts_match_query:', fts_match_query)

async def main():
    async with async_session_maker() as db:
        sql = """SELECT chunk_id, filename, chunk_index, content, bm25(fts_project_documents) as rank
                 FROM fts_project_documents
                 WHERE fts_project_documents MATCH :q AND project_id = :pid"""
        try:
            r = (await db.execute(text(sql), {'q': fts_match_query, 'pid': '10751429-c6ce-40a3-a700-45df4946909f'})).fetchall()
            print('FTS rows:', len(r))
            for row in r[:3]:
                print(' ', row[1], row[2])
        except Exception as e:
            print('FTS error:', e)

        # Check candidate chunks via ORM
        stmt = select(ProjectDocumentChunk).where(ProjectDocumentChunk.project_id == '10751429-c6ce-40a3-a700-45df4946909f')
        all_chunks = (await db.execute(stmt)).scalars().all()
        print('Total ORM chunks for project:', len(all_chunks))
        for ch in all_chunks:
            if 'csv' in ch.filename.lower() or 'csv' in ch.content.lower():
                print(' Matched CSV chunk:', ch.filename, 'Content snippet:', ch.content[:100])

asyncio.run(main())
