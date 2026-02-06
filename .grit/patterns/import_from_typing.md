---
level: warn
tags: [fix]
  ---
# Import symbols from `typing` directly instead of `import typing; typing.foo`

```grit
language python

`typing.$symbol` where {
  add_import($symbol, "typing")
} => $symbol
```
