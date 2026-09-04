# Header branding

The header renders your organisation's logo if you drop a file in **this folder**
named one of:

    logo.svg    (preferred — stays sharp at any size)
    logo.png
    logo.jpg
    logo.webp

It is displayed at up to 3rem tall / 14rem wide. Nothing else needs changing —
the app picks it up on the next page load.

No logo is bundled. A company's logo is its own asset to supply; reproducing a
trademark from a screenshot is not something to bake into source code. Until you
add one, the header simply omits it and the layout closes up cleanly.

## Text wordmark instead

If you would rather show the name as text, set an environment variable and
supply no image file:

    # PowerShell
    $env:DIGEST_ORG_NAME = "Your Organisation"
    python run_webapp.py

That renders an uppercase letter-spaced wordmark in the same slot.
