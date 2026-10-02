# libtailscale patches

Patches apply in filename order to the exact commit in `libtailscale.ref`.
`0001-official-tailscale-version.patch` pins official Tailscale v1.102.5, its
transitive Go dependencies, and Go 1.27.1. It also updates upstream test imports
for the integration package name in that release. The build fails on a patch
conflict; upstream source is never checked into this wrapper repository.

Our Apple bridge is an additive overlay from `Bridge/`. Keep modifications to
existing upstream files as patches here. Update `Tailscale.version` and the
locked dependency patch together when upgrading Tailscale.
