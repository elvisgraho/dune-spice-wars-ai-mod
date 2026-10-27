"""Diagnostic identities stay stable while source locations follow moved code."""
import sys
import unittest

from inject import _src_mod, _trap_src


def probe():
    return _trap_src(), _src_mod(sys._getframe(1))


def source_of(name, group=None):
    namespace = {'probe': probe}
    if group is not None:
        namespace['RULE_LOG_GROUP'] = group
    exec(compile(f'def {name}():\n    return probe()\n', '/rules/casting.py', 'exec'), namespace)
    return namespace[name]()


class RuleSourceTests(unittest.TestCase):
    def test_default_identity_uses_physical_module(self):
        self.assertEqual(source_of('build_example'), ('casting.build_example', 'casting'))

    def test_stable_identity_preserves_physical_source_location(self):
        self.assertEqual(source_of('build_example', 'opsbrain'), ('opsbrain.build_example', 'casting'))

    def test_non_builder_fallback_uses_the_stable_identity(self):
        self.assertEqual(source_of('ordinary', 'opsbrain'), ('opsbrain.ordinary', 'casting'))


if __name__ == '__main__':
    unittest.main()
