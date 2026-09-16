# Official SEC event adapter amendment

This checkpoint connects Event8 to the SEC current-filings Atom feed and changes SEC/volume strategies to use prospective quote reactions rather than invented sentiment.

Before deployment, configure a compliant SEC identity privately on Fly:

`fly secrets set SEC_USER_AGENT='browserbot research your-email@example.com' -a schwab`

The email is an operational contact required by SEC fair-access guidance. Do not commit it. The adapter is read-only, polls no faster than every 30 seconds, labels SEC direction `UNKNOWN`, preserves official timestamps and source URLs, and never submits broker orders.
