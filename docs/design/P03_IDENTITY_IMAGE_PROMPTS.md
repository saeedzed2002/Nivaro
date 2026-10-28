# P03 identity reference provenance — 2026-10-28

Created using built-in image generation, not competitor screenshots. Each image was inspected before any corresponding page implementation. Workspace copies are under `pages/`; original generated outputs remain preserved in the app's generated-image directory. These are layout references, not real customer data or working authentication. Detailed corrective notes are in `PAGE_DESIGNS.md`.

## Shared generation brief (recorded summary)

High-fidelity Nivaro Gaming UI, Persian RTL desktop dark canvas plus white/light mobile inset. Ink `#080A10`, charcoal `#111722`, royal blue `#2563EB`, sky `#72B6FF`; sparse red/purple/indigo/green RGB confined to hardware accents, never green dominant. Vazirmatn-style readable Persian typography, deliberate space and concise controls. Compact branded header with store/language/theme access. No fabricated prices, rewards, reviews or sales. Keep the established visual system rather than redesigning it.

| Reference | Page-specific brief (recorded summary) | Original output |
| --- | --- | --- |
| `pages/customer-login.png` | Split desktop hardware photograph and phone-login form; country context, number input, request code; mobile OTP verification, resend countdown, change number, inline error; explicit local mock disclosure; no customer password/social login | `exec-a2de3c06-c9eb-4072-9659-91129530a6e2.png` |
| `pages/account-overview.png` | Sidebar overview/profile/addresses/logout; two useful profile/address shortcuts; restrained hardware banner; all-device logout explanation and confirmation; no invented order/loyalty metrics | `exec-ace007da-27e1-4c38-8aef-7b9457e9c85b.png` |
| `pages/account-profile.png` | Name form, read-only verified phone, initials placeholder, no upload control; save/cancel and validation/success; profile image processing later; no customer password-change form | `exec-b3d80933-becb-4b5d-a939-32b193cc5cab.png` |
| `pages/account-addresses.png` | Empty address state and add form: label, recipient, country, city, postal code, street, contact phone; mobile stacked white form; validation, cancel/save, deletion confirmation; no real personal data or fulfillment claims | `exec-4b7a5610-b04c-4c90-a0df-f03dd4a9a215.png` |
| `pages/admin-login.png` | Separate staff login, restrained central credential panel, email/password/show control, blue submit, generic error, store link; no signup, OTP, default password, certification or unimplemented reset flow | `exec-7f4ba5a9-4c1d-448c-bb85-040d34a1a85c.png` |

Generated output did not follow every detail literally: six separate OTP cells appeared despite a one-input request; extra commerce navigation and example user values appeared; the all-device dialog added an incorrect current-device exception. These are rejected details, documented in the register. Use one accessible OTP input, actual account data, implemented routes only, and the canonical session contract when coding.
