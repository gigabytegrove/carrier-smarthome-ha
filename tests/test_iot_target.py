"""Offline source/CLI contract checks for the dedicated Windows IoT scanner.

The actual PowerShell execution tests are in Test-IoTDiscovery.ps1 and should
be run on Windows, where Windows network cmdlets are available.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
IOT = (ROOT / 'tools' / 'Discover-CarrierIoT.ps1').read_text(encoding='utf-8')
RUNNER = (ROOT / 'tools' / 'Run-Discovery.ps1').read_text(encoding='utf-8')

class IoTTargetContract(unittest.TestCase):
    def test_default_target_is_confirmed_vlan(self):
        self.assertIn("[string]$Subnet = '172.20.0.0/16'", IOT)
        self.assertIn("[string]$IoTSubnet = '172.20.0.0/16'", RUNNER)

    def test_main_script_does_not_run_other_lans_by_default(self):
        self.assertIn('[switch]$IncludeOtherNetworks', RUNNER)
        self.assertIn('if ($IncludeOtherNetworks) {', RUNNER)
        self.assertIn("'Discover-CarrierIoT.ps1'", RUNNER)

    def test_subnet_restricted_and_full_default_sweep(self):
        self.assertIn("ConvertTo-Number '172.20.0.0'", IOT)
        self.assertIn("ConvertTo-Number '172.20.255.255'", IOT)
        self.assertIn('Refusing to scan outside the user-confirmed', IOT)
        self.assertIn('for ([uint64]$offset = 0;', IOT)

    def test_no_write_or_device_api_calls(self):
        for call in ('Invoke-RestMethod', 'Invoke-WebRequest', 'Set-Net', 'Send-Mqtt', 'Set-Item'):
            self.assertNotIn(call, IOT)
        self.assertIn('SendPingAsync', IOT)
        self.assertIn('ConnectAsync', IOT)

    def test_silent_host_tcp_requires_deep(self):
        self.assertRegex(IOT, r'if \(\$Deep -and -not \$NoTcp\)')
        self.assertIn('tcp_silent_host_coverage =', IOT)

    def test_plan_mode_before_any_icmp_tcp(self):
        self.assertLess(IOT.index('if ($PlanOnly) {'), IOT.index('Invoke-PingBatch $batch.ToArray()'))
        self.assertIn('if (-not $SkipPublicCloud -and -not $PlanOnly)', RUNNER)

if __name__ == '__main__':
    unittest.main()
