"""DEX opcode/string value correctness tests without distributing the APK."""
import importlib.util
from pathlib import Path
import struct
import sys
import unittest

SRC = Path(__file__).resolve().parents[1] / 'research'
sys.path.insert(0, str(SRC))
spec = importlib.util.spec_from_file_location('carrier_trace', SRC / 'trace_native_constants.py')
trace = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = trace
spec.loader.exec_module(trace)

class DEXTests(unittest.TestCase):
    def test_encoded_value_string_id(self):
        # value-type 0x17: string index 0x0123 (two bytes, little-endian)
        value, next_position = trace.parse_encoded_value(bytes([0x37, 0x23, 0x01]), 0)
        self.assertEqual(value, [0x123])
        self.assertEqual(next_position, 3)

    def test_encoded_null(self):
        self.assertEqual(trace.parse_encoded_value(b'\x1e', 0), ([], 1))

    def test_encoded_array(self):
        data = bytes([0x1c, 2, 0x17, 8, 0x17, 9])
        self.assertEqual(trace.parse_encoded_value(data, 0), ([8, 9], len(data)))

    def test_code_item_const_string(self):
        instructions = [0x000e, 0x001a, 0x1234, 0x000e]  # return, const-string, string index, return
        code = bytearray(16 + len(instructions)*2)
        struct.pack_into('<I', code, 12, len(instructions))
        struct.pack_into('<'+'H'*len(instructions), code, 16, *instructions)
        self.assertEqual(trace.method_constants(bytes(code), 0, {0x1234}), {0x1234})

    def test_no_operand_false_positive(self):
        instructions = [0x0013, 0x001a, 0x000e]  # const/16 operand low byte happens to be 0x1a
        code = bytearray(16 + len(instructions)*2)
        struct.pack_into('<I', code, 12, len(instructions))
        struct.pack_into('<'+'H'*len(instructions), code, 16, *instructions)
        self.assertEqual(trace.method_constants(bytes(code), 0, {0x000e}), set())

    def test_public_ats_hostname_whitelist(self):
        self.assertTrue(trace.SAFE_AWS_ENDPOINT.fullmatch('a2pznvrwmtzhom-ats.iot.us-east-1.amazonaws.com'))
        self.assertFalse(trace.SAFE_AWS_ENDPOINT.fullmatch('example.com'))
        self.assertNotIn('DUCTLESS_ROOT_KEY', trace.SAFE_BUILD_CONFIG_FIELDS)

if __name__ == '__main__':
    unittest.main()
