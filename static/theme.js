(() => {
  const themeKey = "spending-tracker-theme";
  const root = document.documentElement;

  const preferencesAllowed = () =>
    Boolean(window.cookieConsent && window.cookieConsent.allowsPreferences());

  try {
    const savedTheme = preferencesAllowed() ? localStorage.getItem(themeKey) : null;
    if (savedTheme === "light" || savedTheme === "dark") {
      root.dataset.theme = savedTheme;
    }
  } catch (error) {
    console.warn("Could not load the saved display theme:", error);
  }

  function currentTheme() {
    return root.dataset.theme
      || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  }

  function updateThemeButton() {
    const button = document.getElementById("theme-toggle");
    if (button) {
      button.textContent = `Use ${currentTheme() === "dark" ? "light" : "dark"} mode`;
    }
  }

  function saveTheme() {
    try {
      if (preferencesAllowed() && root.dataset.theme) {
        localStorage.setItem(themeKey, root.dataset.theme);
      } else {
        localStorage.removeItem(themeKey);
      }
    } catch (error) {
      console.warn("Could not save the display theme:", error);
    }
  }

  // Granting consent keeps the theme chosen this visit; withdrawing it erases it.
  document.addEventListener("cookieconsentchange", saveTheme);

  document.addEventListener("DOMContentLoaded", () => {
    updateThemeButton();
    const profileMenu = document.querySelector(".profile-menu");
    if (profileMenu) {
      document.addEventListener("click", (event) => {
        if (!profileMenu.contains(event.target)) profileMenu.open = false;
      });
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && profileMenu.open) {
          profileMenu.open = false;
          profileMenu.querySelector("summary").focus();
        }
      });
    }

    const button = document.getElementById("theme-toggle");
    if (!button) return;

    button.addEventListener("click", () => {
      const theme = currentTheme() === "dark" ? "light" : "dark";
      root.dataset.theme = theme;
      updateThemeButton();
      saveTheme();
    });
  });
})();
