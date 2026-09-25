import tempfile,unittest
from pathlib import Path
import web.app as module
from web.schema import initialize_database
class SchemaTests(unittest.TestCase):
    def test_source_seen_at_is_present_and_populated(self):
        with tempfile.TemporaryDirectory() as tmp:
            old=module.DB; module.DB=str(Path(tmp)/'schema.sqlite3')
            try:
                initialize_database(module.db)
                with module.db() as c: self.assertIn('source_seen_at',{r[1] for r in c.execute('PRAGMA table_info(leads)')})
                module.add_lead({'name':'Schema fixture','city':'Fixture City','phone':'0000000000','website':''})
                with module.db() as c: self.assertTrue(c.execute('SELECT source_seen_at FROM leads WHERE name=?',('Schema fixture',)).fetchone()[0])
            finally: module.DB=old
if __name__=='__main__': unittest.main()
