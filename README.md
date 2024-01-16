# Grafana Known Issues

This is a simple python script to go through bugs in grafana/grafana and figure out if there is a known version that this is being reported by.

- get list of issues with `type/bug` label
- filter issues with a line that starts with `Grafana:` as that is what is in our template
- group by version
- generate a report.md file
