# Rule table

Eight rules, programmable at run time without a rebuild. People and the agent write a rule as JSON
(`rules/rule_schema.json`); `model/rules.py` validates it and turns it into six register words; the host writes them
to the shadow table and commits (`docs/register_map.md`). `host/nl_rule.py` is the natural-language step.

## Semantics

A rule is checked on every market-data message at the moment its price field is complete (8 bytes into the
message). All enabled rules are checked at once; the lowest-numbered rule that matches and is not in hold-off fires.
At most one rule fires per message, and at most one order is requested per received frame.

A rule matches when all of these hold:

- the message type is in the rule's type set;
- the message side is the rule's side (or the rule says any);
- the instrument is the rule's (or the rule says any);
- the price comparison holds (`<`, `<=`, `>`, `>=` against the threshold), if the rule has one;
- the book condition holds, if any: **improves** = a bid above the best bid or an ask below the best ask (or that
  side is empty); **crosses** = a bid at or above the best ask, or an ask at or below the best bid (the other side not
  empty). The book is the instrument's state before this message.

A rule's hold-off is the minimum number of clocks before the same rule may fire again (hold-offs restart when a new
table is committed). Examples of the book conditions: with a best ask of 100.00, a bid at 100.00 or above **crosses**;
with a best bid of 99.50, a new bid at 99.60 **improves** its side.

When it fires it can send an order (buy or sell, a quantity, a price that is fixed, the message's price, or the
message's price plus a signed offset), raise a pin for PIN_WIDTH clocks, and log the decision. An order then passes
the interlocks (`rtl/interlocks.sv`); its price band is checked against the book before the triggering message, never
against the message itself.

## Words

| Word | Bits |
|---|---|
| 0 control | [0] enable, [1] ADD, [2] MODIFY, [3] CANCEL, [4] TRADE, [6:5] side (0 any, 1 bid, 2 ask), [7] any instrument, [10:8] compare (0 none, 1 <, 2 <=, 3 >, 4 >=), [12:11] book (0 none, 1 improves, 2 crosses), [13] order, [14] order side (0 buy, 1 sell), [16:15] order price (0 fixed, 1 message, 2 message + offset), [17] pin, [18] which pin, [19] log |
| 1 | instrument [15:0] |
| 2 | price threshold (hundredths of a price unit) |
| 3 | order quantity |
| 4 | fixed price, or the signed offset (two's complement), in hundredths of a price unit |
| 5 | hold-off, in 8 ns clocks |

## What the validator refuses (beyond the schema)

- a price with more than two decimals;
- an order larger than the interlocks' maximum size (every order would be refused);
- an offset larger than the price band, or a fixed price further than the band from the rule's own threshold;
- a rule that does nothing (no order, no pin, no log).

The interlocks enforce the same limits again in hardware: the validator only saves loading a rule that could never
send anything.
