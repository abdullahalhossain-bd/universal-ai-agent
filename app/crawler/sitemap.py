from xml.etree import ElementTree


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

    except ElementTree.ParseError:

        return []

    return urls
