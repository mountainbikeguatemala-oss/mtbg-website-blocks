# The photo server's https front: the official Caddy image with the Cloudflare DNS module (certificates by DNS-01,
# so the NAS needs no port open to the internet). Built here, tagged tour-photos-tls:2.10.2-cf.
# CADDY_DNS_CLOUDFLARE pins the module (e.g. --build-arg CADDY_DNS_CLOUDFLARE=v0.2.2); empty = its latest release.
FROM caddy:2.10.2-builder AS build
ARG CADDY_DNS_CLOUDFLARE=
RUN xcaddy build --with "github.com/caddy-dns/cloudflare${CADDY_DNS_CLOUDFLARE:+@$CADDY_DNS_CLOUDFLARE}"

FROM caddy:2.10.2
COPY --from=build /usr/bin/caddy /usr/bin/caddy
