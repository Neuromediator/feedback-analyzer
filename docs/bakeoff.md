# Model bake-off

Dataset: 100 synthetic reviews (`eval/dataset.jsonl`), batches of 25, 4 concurrent, default theme list. Targets: label >= 90%, score +/-1 >= 85%, theme >= 80%, clean batches >= 99%, cost < $0.05 per 100 reviews, time < 30 s.

| Candidate | Label acc | Score +/-1 | Theme acc | Failed | Clean calls | Cost / 100 | Time | Meets all | Served by |
|---|---|---|---|---|---|---|---|---|---|
| haiku-5.5 | 98% | 100% | 100% | 0 | 100% | $0.0025 | 6.1 s | yes | anthropic/claude-haiku-5.5 |
| haiku-5.5 low | 97% | 100% | 100% | 0 | 100% | $0.0021 | 2.7 s | yes | anthropic/claude-haiku-5.5 |
| gpt-6-luna | 99% | 100% | 100% | 0 | 100% | $0.0020 | 6.2 s | yes | openai/gpt-6-luna |
| gpt-6-luna low | 98% | 100% | 100% | 0 | 100% | $0.0018 | 14.0 s | yes | openai/gpt-6-luna |
| deepseek-v4.1-flash | 100% | 100% | 100% | 0 | 100% | $0.0056 | 16.0 s | yes | deepseek/deepseek-v4.1-flash-1017 |
| gemini-3.5-flash-lite | 98% | 100% | 100% | 0 | 100% | $0.0100 | 2.2 s | yes | google/gemini-3.5-flash-lite |
| jev-router | 100% | 100% | 100% | 0 | 100% | $0.0213 | 23.6 s | yes | deepseek/deepseek-v4.1-flash-1017, google/gemini-3.8-flash, x-ai/grok-4.7 |
| jev-1.14 | 99% | 100% | 100% | 0 | 100% | $0.0025 | 3.9 s | yes | typesafe/jev-1.14-20261014 |
| jev-1.13 | 99% | 100% | 100% | 0 | 100% | $0.0025 | 3.3 s | yes | typesafe/jev-1.13-20260917 |

Label accuracy by review kind:

| Candidate | emoji | mixed | no_theme | non_english | normal | sarcasm | short | typos |
|---|---|---|---|---|---|---|---|---|
| haiku-5.5 | 83% | 90% | 100% | 100% | 100% | 100% | 100% | 100% |
| haiku-5.5 low | 83% | 90% | 100% | 100% | 98% | 100% | 100% | 100% |
| gpt-6-luna | 83% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| gpt-6-luna low | 83% | 100% | 86% | 100% | 100% | 100% | 100% | 100% |
| deepseek-v4.1-flash | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| gemini-3.5-flash-lite | 83% | 100% | 100% | 100% | 100% | 100% | 88% | 100% |
| jev-router | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| jev-1.14 | 100% | 100% | 100% | 100% | 98% | 100% | 100% | 100% |
| jev-1.13 | 100% | 100% | 100% | 100% | 98% | 100% | 100% | 100% |

Default-model rule (cheapest that meets all targets): **gpt-6-luna low**
