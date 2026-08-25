# `wopr.yml` schema — moved

The schema document now lives at
[`catalog/crew/templates/wopr-yml-schema.md`](../catalog/crew/templates/wopr-yml-schema.md).

It moved into the crew pack's `templates/` tree so that it **ships**: that
directory is bundled into the wopr-crew plugin and the server resources, which
makes the schema reachable in every install via
`get_pack_template(pack="crew", name="wopr-yml-schema.md")`. A `docs/`-only
file exists in a repo checkout and nowhere else, and every shipped reference to
it was a dead path.

This pointer stays for link stability; do not add content here.
