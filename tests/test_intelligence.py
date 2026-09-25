import unittest
from web.intelligence import _fit

class IntelligenceFitTests(unittest.TestCase):
    def test_known_sector_returns_build_direction(self):
        result = _fit('Dental Clinic')
        self.assertEqual(result['goal'], 'Appointments')
        self.assertIn('Treatments', result['pages'])
        self.assertIn('Book appointment CTA', result['modules'])

    def test_unknown_sector_is_safe_and_useful(self):
        result = _fit('Independent artisan studio')
        self.assertEqual(result['goal'], 'Qualified enquiry')
        self.assertIn('Home', result['pages'])
        self.assertIn('Verified proof', result['modules'])

if __name__ == '__main__':
    unittest.main()
