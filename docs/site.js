const repo = {
  owner: "krahd",
  name: "Mail-Summariser",
};

const latestReleaseLabel = document.getElementById("latest-release-label");
const releasePageLink = document.getElementById("release-page-link");
const downloadsStatus = document.getElementById("downloads-status");

function setStatus(message, isError = false) {
  if (!downloadsStatus) {
    return;
  }
  downloadsStatus.textContent = message;
  downloadsStatus.style.color = isError ? "#b5312e" : "#5f6963";
}

function updateAssetLink(assetName, href) {
  const link = document.querySelector(`[data-asset="${assetName}"]`);
  if (!link) {
    return;
  }
  link.href = href;
}

function updateSourceLink(kind, href) {
  const link = document.querySelector(`[data-source="${kind}"]`);
  if (!link) {
    return;
  }
  link.href = href;
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
    const assets = Array.isArray(release.assets) ? release.assets : [];
    const assetsByName = new Map(assets.map((asset) => [asset.name, asset.browser_download_url]));
    const tagName = release.tag_name || "latest";

    if (latestReleaseLabel) {
      latestReleaseLabel.textContent = tagName;
    }
    if (releasePageLink && release.html_url) {
      releasePageLink.href = release.html_url;
    }

    updateAssetLink(
      "mail-summariser-backend-macos-arm64.tar.gz",
      assetsByName.get("mail-summariser-backend-macos-arm64.tar.gz") || release.html_url
    );
    updateAssetLink(
      "MailSummariser-macos-app.zip",
      assetsByName.get("MailSummariser-macos-app.zip") || release.html_url
    );
    updateAssetLink(
      "mail-summariser-backend-windows-x64.zip",
      assetsByName.get("mail-summariser-backend-windows-x64.zip") || release.html_url
    );
    updateAssetLink(
      "mail-summariser-backend-linux-x64.tar.gz",
      assetsByName.get("mail-summariser-backend-linux-x64.tar.gz") || release.html_url
    );

    updateSourceLink("zip", `https://github.com/${repo.owner}/${repo.name}/archive/refs/tags/${tagName}.zip`);
    updateSourceLink("tar", `https://github.com/${repo.owner}/${repo.name}/archive/refs/tags/${tagName}.tar.gz`);

    setStatus(`Latest release ${tagName} loaded. Download links now point at the newest published assets.`);
  } catch (error) {
    if (latestReleaseLabel) {
      latestReleaseLabel.textContent = "Unavailable";
    }
    setStatus(
      `Could not load the latest release automatically. Use the release page link instead. ${error.message}`,
      true
    );
  }
}

initDownloads();