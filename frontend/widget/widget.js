(function () {

    const script =
        document.currentScript;

    const apiKey =
        script.dataset.apiKey;

    if (!apiKey) {
        console.error(
            "AI Widget: API key missing"
        );
        return;
    }

    const iframe =
        document.createElement("iframe");

    iframe.src =
        "https://chat.yourdomain.com/?key="
        + encodeURIComponent(apiKey);

    iframe.style.position = "fixed";
    iframe.style.right = "20px";
    iframe.style.bottom = "20px";

    iframe.style.width = "380px";
    iframe.style.height = "600px";

    iframe.style.border = "none";

    iframe.style.zIndex = "2147483647";

    iframe.allow =
        "clipboard-write";

    document.body.appendChild(
        iframe
    );

})();
