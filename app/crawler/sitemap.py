# Sitemaps are fetched from arbitrary, untrusted third-party websites during
# crawling, so this must not use the stdlib xml.etree.ElementTree parser
# directly: it has no protection against entity-expansion ("billion laughs")
# or quadratic-blowup denial-of-service payloads embedded in a DOCTYPE.
# defusedxml wraps the same ElementTree API but rejects DTDs/entities outright.
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException


def parse_sitemap(xml_text: str):

    urls = []

    try:

        root = ElementTree.fromstring(
            xml_text
        )

        for elem in root.iter():

            if elem.tag.endswith("loc"):

                if elem.text:
                    urls.append(
                        elem.text.strip()
                    )

    except (ElementTree.ParseError, DefusedXmlException):

        return []

    return urls
