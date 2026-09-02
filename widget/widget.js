(function () {

    const script =
        document.currentScript;

    const apiKey =
        script.dataset.apiKey;

    const apiUrl =
        script.dataset.apiUrl;

    if (!apiKey || !apiUrl) {
        console.error(
            "Chat widget configuration missing"
        );

        return;
    }

    const button =
        document.createElement("button");

    button.innerText = "Chat";

    button.style.position = "fixed";
    button.style.right = "20px";
    button.style.bottom = "20px";

    document.body.appendChild(button);

})();
