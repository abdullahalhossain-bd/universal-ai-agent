class ContextFormatter:

    def format(
        self,
        context,
    ):

        sections = []

        for item in context.items:

            section = (
                f"SOURCE: "
                f"{item.source_type}\n"
            )

            if item.title:

                section += (
                    f"TITLE: "
                    f"{item.title}\n"
                )

            section += (
                f"CONTENT:\n"
                f"{item.content}\n"
            )

            if item.url:

                section += (
                    f"URL: {item.url}\n"
                )

            sections.append(section)

        return "\n---\n".join(
            sections
        )
