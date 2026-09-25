        self.assertIn('What we noticed on your current site', email['html'])
        self.assertIn('No page title found.', email['html'])
        self.assertIn('https://reachmark.example/r/tokf', email['html'])
        self.assertIn('/r/tokf/answer/want', email['html'])
        self.assertIn('logo-primary.png', email['html'])
        # And the website itself stays clean \u2014 no faults, no question.
        with module.db() as c:
            c.execute("INSERT INTO leads(id,source_key,name,category,city,token,created,updated) VALUES('LF','kf','Faulty Bakes','Bakery','Demo','tokf',?,?)",
                      (module.now(), module.now()))
        link_row = create_link(module.db, module.now, lead, {'theme': 'ember'}, 'share')
        page = self.client.get('/r/' + link_row['token'])
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b'What we noticed on your current site', page.data)
        self.assertNotIn(b'What we noticed on your current site', page.data)
        self.assertIn(b'Would you like this built', page.data)
        self.assertIn(b'Yes — build my website', page.data)
        self.assertIn(b'Not right now', page.data)
        self.assertIn(b'I already have a website', page.data)


if __name__ == '__main__':
    unittest.main()