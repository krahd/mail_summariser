const repo = {
  owner: "krahd",
  name: "mail_summariser",
};

const releasePageLink = document.getElementById("release-page-link");
const downloadsStatus = document.getElementById("downloads-status");

function setStatus(message, isError = false) {
  if (!downloadsStatus) {
    return;
  }
  downloadsStatus.textContent = message;
  downloadsStatus.style.color = isError ? "#9b3d31" : "#53665f";
}

function setLink(selector, href) {
  const link = document.querySelector(selector);
  if (link && href) {
    link.href = href;
  }
}

async function loadLatestRelease() {
  const response = await fetch(`https://api.github.com/repos/${repo.owner}/${repo.name}/releases/latest`, {
    headers: { Accept: "application/vnd.github+json" },
  });

  if (!response.ok) {
    throw new Error(`GitHub API returned ${response.status}`);
  }

  return response.json();
}

async function initDownloads() {
  try {
    const release = await loadLatestRelease();
    const tagName = release.tag_name || "latest";
    const releaseUrl = release.html_url || `https://github.com/${repo.owner}/${repo.name}/releases/latest`;
    const assets = Array.isArray(release.assets) ? release.assets : [];
    const assetsByName = new Map(assets.map((asset) => [asset.name, asset.browser_download_url]));

    if (releasePageLink) {
      releasePageLink.href = releaseUrl;
    }

    for (const [assetName, href] of assetsByName.entries()) {
      setLink(`[data-asset="${assetName}"]`, href);
    }

    setLink("[data-source='zip']", `https://github.com/${repo.owner}/${repo.name}/archive/refs/tags/${tagName}.zip`);
    setLink("[data-source='tar']", `https://github.com/${repo.owner}/${repo.name}/archive/refs/tags/${tagName}.tar.gz`);
    setStatus(`Latest release ${tagName} loaded. Download links now point at published assets.`);
  } catch (error) {
    setStatus(`Could not load release metadata automatically. Use the release page link. ${error.message}`, true);
  }
}

initDownloads();
