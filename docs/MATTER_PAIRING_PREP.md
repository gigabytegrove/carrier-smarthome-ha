# Save your thermostat's Smart Home pairing code before mounting

This simple guide applies to the **Carrier Smart Thermostat TSTATCCEWF-01**.
You can set up the **Carrier SmartHome Home Assistant integration without any
Matter code**: it signs in to Carrier's cloud and uses your Carrier account
credentials. Read this guide if you might also use a separate Matter
controller (such as Aveliom), now or later.

## Before the thermostat is mounted

1. Find the **Smart Home** label on the back of the thermostat. Carrier
   explicitly documents that the Smart Home QR code is on the rear housing.
2. Take a clear **private photo** of that label, including the entire QR
   image and any human-readable setup code. If an **11-digit or 21-digit
   Matter manual pairing code** is supplied, write it down accurately.
   Keep the installation sheet or the installer's copy of the code too.
3. The **Mobile Onboarding** QR code, sometimes shown on the original
   hang tag or in installation instructions, is **not the same as** the
   Smart Home / Matter code.
4. Complete Carrier's regular thermostat installation and Wi-Fi onboarding
   using the official instructions. The thermostat must be installed,
   powered and connected when it actually pairs with a Matter controller.
   Saving the QR photo **does not require** leaving the thermostat powered.

## Already mounted and powered?

- If you saved the **Matter manual code**, enter the digits in a compatible
  controller's manual code field. With Aveliom, hyphens and spaces are OK.
  **You do not need a live QR scan or to remove the thermostat.**
- If you saved the Smart Home QR photo but no manual code, use a compatible
  controller's supported QR onboarding flow while the thermostat remains
  mounted; some apps allow presenting the photo on a second screen to scan.
  Aveliom supports pasting a valid `MT:...` QR payload, but does not yet
  process a photograph into a QR payload.
- If you have **neither**, check installation paperwork, packaging,
  photos and installer records first. There is no verified Carrier API
  endpoint or cloud-integration feature that can reconstruct the missing
  Matter setup secret. For another retrieval option, contact Carrier or
  your installer rather than attempting unapproved physical work.
- Do not detach the thermostat while powered, reset the HVAC configuration
  or factory-reset it just to make the code visible. If physical access
  becomes necessary, follow Carrier's safety instructions or use a
  qualified installer.

## Understanding Matter pairing mode

**The QR/manual setup code identifies the device, but does not make
it discoverable.** A separate, currently active Matter commissioning
window is required. Carrier's Bluetooth setup instructions (such as a
blinking blue indicator) are not proof that a Matter commissioning window
has opened. We have **not verified** a specific Carrier TSTATCCEWF-01
button sequence for opening a Matter commissioning window on an
already-configured thermostat. Follow Carrier's supported instructions
for your hardware; do not change installer/HVAC settings experimentally.

Aveliom currently supports **network-only Matter commissioning**. A
device that requires initial Bluetooth network provisioning or that is
not advertising Matter on the reachable IPv6/mDNS network may not pair.
A `not-discovered` error means the controller did not see a commissionable
device; it does not establish that the code is wrong.

## Important: what Home Assistant integration do I install?

- **Carrier SmartHome (this GitHub repository):** Uses Carrier's cloud,
  requires Carrier account username/password, and does **not** use the
  Matter code. It can be set up without touching the thermostat label.
- **An independent Matter controller/integration:** May use the saved
  Smart Home / Matter code and needs an open Matter commissioning window.
  This is a separate onboarding procedure and is **not built into** this
  Carrier SmartHome custom integration.

## References

- Carrier TSTATCCEWF-01 installation instructions (Smart Home ready,
  QR location on back of thermostat):
  https://assets-f02205d260.cdn.insitecloud.net/61e56e8270b9de4/TSTATCCEWF-01SI-%20Installation%20Instructions.pdf
- Carrier Smart Thermostat brochure:
  https://www.shareddocs.com/hvac/docs/1010/Public/07/01-TSTAT-113-01.pdf

## Phone-based Matter commissioning without pulling it off the wall

For an already installed and powered thermostat with a *saved* Matter
manual setup code, Google's official Android guide supports
**Google Home → Add device → Matter-enabled device → Set up without QR code**.
Enter the code manually; a live QR scan is not required.
Google Home may use the phone's Bluetooth features for first commissioning.
**This is a troubleshooting option, not a verified Carrier-specific method for
opening an already-configured thermostat's Matter commissioning window.**
If no Matter device is discovered, stop and consult Carrier.

If Google Home *successfully adds it as a Matter device* (not merely by
linking your Carrier cloud account), open the device's Google Home settings →
**Linked Matter apps & services** → **Link apps & services** →
**Use pairing code**. Enter that new, temporary sharing code in Aveliom
while the multi-admin commissioning window is open.

Official Google instructions:
https://support.google.com/googlehome/answer/13127223

Remember: **this Carrier SmartHome Home Assistant integration itself
requires only Carrier cloud credentials and never uses a Matter code**.
