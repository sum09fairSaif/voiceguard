"""Dev tool: send one real test email through email_sender.py, to check the
Resend settings work and the email lands in the inbox, not spam.

From backend/, with the venv active and EMAIL_API_KEY and EMAIL_FROM in
.env (the same values as on Render):

    python scripts/send_test_email.py you@example.com

With EMAIL_FROM=onboarding@resend.dev (no domain verified yet), Resend only
delivers to the address the Resend account was made with.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_sender import EmailUnavailable, get_email_sender


def main(to: str) -> None:
    try:
        get_email_sender()(
            to,
            "VoiceGuard test email",
            "This is a test email from VoiceGuard's backend. If it reached your inbox, sending works.",
            "test",
        )
    except EmailUnavailable as exc:
        sys.exit(f"Not sent: {exc}")
    print("Sent. Check the inbox, and the spam folder if it isn't there.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
