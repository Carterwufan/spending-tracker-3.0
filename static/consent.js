(() => {
  const cookieName = "cookie_consent";
  const maxAgeSeconds = 60 * 60 * 24 * 180;
  const choices = ["essential", "preferences"];

  function readChoice() {
    const match = document.cookie
      .split("; ")
      .find((part) => part.startsWith(`${cookieName}=`));
    const value = match ? match.slice(cookieName.length + 1) : null;
    return choices.includes(value) ? value : null;
  }

  function saveChoice(choice) {
    const secure = location.protocol === "https:" ? "; Secure" : "";
    document.cookie =
      `${cookieName}=${choice}; Max-Age=${maxAgeSeconds}; Path=/; SameSite=Lax${secure}`;
    document.dispatchEvent(
      new CustomEvent("cookieconsentchange", { detail: { choice } })
    );
  }

  window.cookieConsent = {
    allowsPreferences: () => readChoice() === "preferences",
  };

  document.addEventListener("DOMContentLoaded", () => {
    const banner = document.getElementById("cookie-banner");
    if (!banner) return;

    if (readChoice() === null) banner.hidden = false;

    banner.querySelectorAll("[data-consent]").forEach((button) => {
      button.addEventListener("click", () => {
        saveChoice(button.dataset.consent);
        banner.hidden = true;
        document.getElementById("cookie-settings")?.focus();
      });
    });

    document.getElementById("cookie-settings")?.addEventListener("click", () => {
      banner.hidden = false;
      const current = readChoice() || "essential";
      banner.querySelector(`[data-consent="${current}"]`).focus();
    });
  });
})();
