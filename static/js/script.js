document.addEventListener("DOMContentLoaded", () => {
  function normalizePath(path) {
    if (!path) {
      return "/";
    }
    return path.replace(/\/+$/, "") || "/";
  }

  const currentPath = normalizePath(window.location.pathname);
  const navLinks = document.querySelectorAll(".sector-item a, .mobile-bottom-nav a");

  navLinks.forEach(link => {
    const rawHref = link.getAttribute("href") || "";

    if (rawHref.startsWith("#")) {
      const target = document.querySelector(rawHref);
      link.addEventListener("click", event => {
        if (!target) {
          return;
        }
        event.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      return;
    }

    const resolved = new URL(rawHref, window.location.origin);
    const linkPath = normalizePath(resolved.pathname);
    const isActive = linkPath === currentPath;

    link.classList.toggle("active", isActive);
    if (link.parentElement?.classList.contains("sector-item")) {
      link.parentElement.classList.toggle("active", isActive);
    }

    if (isActive) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
});
