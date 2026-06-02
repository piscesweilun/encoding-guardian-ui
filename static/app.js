const state = {
  root: "",
  files: [],
  filter: "all",
  browsePath: "",
  browseParent: "",
};

const el = (id) => document.getElementById(id);

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function isNonUtf8(file) {
  return !["utf-8", "utf-8-sig"].includes(file.encoding);
}

function matchesFilter(file) {
  switch (state.filter) {
    case "big5":
      return file.encoding === "cp950";
    case "non-utf8":
      return isNonUtf8(file);
    case "unknown":
      return file.encoding === "unknown";
    case "low-confidence":
      return file.confidence === "low";
    case "convertible":
      return file.selectable;
    default:
      return true;
  }
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

function renderStats(counts = {}) {
  const entries = [
    ["utf-8", "UTF-8"],
    ["utf-8-sig", "UTF-8 BOM"],
    ["cp950", "CP950 / Big5"],
    ["utf-16-le", "UTF-16 LE"],
    ["utf-16-be", "UTF-16 BE"],
    ["unknown", "Unknown"],
    ["binary", "Binary"],
  ];
  el("stats").innerHTML = entries
    .map(([key, label]) => `<div class="stat"><strong>${counts[key] || 0}</strong><span>${label}</span></div>`)
    .join("");
}

function renderRows() {
  const rows = state.files.filter(matchesFilter);
  if (!rows.length) {
    el("fileRows").innerHTML = `<tr><td colspan="8" class="empty">沒有符合條件的檔案</td></tr>`;
    return;
  }
  el("fileRows").innerHTML = rows
    .map((file, index) => {
      const id = state.files.indexOf(file);
      return `
        <tr>
          <td><input class="file-check" type="checkbox" data-id="${id}" ${file.selected ? "checked" : ""} ${file.selectable ? "" : "disabled"} /></td>
          <td class="path" title="${file.path}">${file.relative_path}</td>
          <td><span class="tag">${file.encoding}</span></td>
          <td>${file.confidence}</td>
          <td>${file.line_ending}</td>
          <td>${formatSize(file.size)}</td>
          <td><span class="tag ${file.risk}">${file.risk}</span></td>
          <td><button data-preview="${id}">預覽</button></td>
        </tr>
      `;
    })
    .join("");
}

function log(message) {
  el("logText").textContent = message;
}

async function browseDirectories(path = "") {
  const data = await postJson("/api/browse", { path });
  state.browsePath = data.path;
  state.browseParent = data.parent;
  el("currentDirectoryText").textContent = data.path || "磁碟機";
  el("parentDirectoryButton").disabled = !data.parent;
  el("directoryList").innerHTML = data.directories.length
    ? data.directories
        .map(
          (directory) => `
            <button class="directory-item" data-path="${directory.path}">
              <span>${directory.name}</span>
              <strong>${directory.isDrive ? "磁碟" : "資料夾"}</strong>
            </button>
          `
        )
        .join("")
    : `<div class="empty">此目錄沒有可瀏覽的子資料夾</div>`;
}

async function openDirectoryDialog() {
  el("directoryDialog").showModal();
  el("directoryList").innerHTML = `<div class="empty">讀取中...</div>`;
  try {
    await browseDirectories(el("rootInput").value.trim());
  } catch (error) {
    log(`讀取目錄失敗：${error.message}`);
    await browseDirectories("");
  }
}

async function scan() {
  el("scanButton").disabled = true;
  el("scanButton").textContent = "掃描中...";
  log("");
  try {
    const payload = {
      root: el("rootInput").value,
      include: el("includeInput").value,
      exclude: el("excludeInput").value,
      maxSizeMb: el("maxSizeInput").value,
      recursive: el("recursiveInput").checked,
    };
    const data = await postJson("/api/scan", payload);
    state.root = data.root;
    state.files = data.files.map((file) => ({
      ...file,
      selected: file.encoding === "cp950" && file.confidence !== "low",
    }));
    renderStats(data.counts);
    renderRows();
    el("reportPath").textContent = data.reportPath ? `CSV: ${data.reportPath}` : "";
    log(`掃描完成：${data.files.length} 個檔案，略過 ${data.skipped.length} 個。`);
  } catch (error) {
    log(`掃描失敗：${error.message}`);
  } finally {
    el("scanButton").disabled = false;
    el("scanButton").textContent = "掃描";
  }
}

async function preview(index) {
  const file = state.files[index];
  if (!file) return;
  el("previewMeta").textContent = file.relative_path;
  el("previewText").textContent = "讀取預覽中...";
  try {
    const data = await postJson("/api/preview", {
      path: file.path,
      fromEncoding: el("fromEncoding").value,
      toEncoding: el("toEncoding").value,
    });
    el("previewText").textContent = [
      `來源：${data.fromEncoding}`,
      `目標：${data.toEncoding}`,
      `文字 roundtrip 一致：${data.sameTextAfterRoundtrip ? "是" : "否"}`,
      `Replacement 字元：${data.replacementCount}`,
      `換行：${data.lineEnding}`,
      `大小：${formatSize(data.sizeBefore)} -> ${formatSize(data.sizeAfter)}`,
      `風險：${data.risk}`,
      "",
      "樣本：",
      data.sample || "(沒有可顯示的文字樣本)",
    ].join("\n");
  } catch (error) {
    el("previewText").textContent = `預覽失敗：${error.message}`;
  }
}

async function convertSelected() {
  const selected = state.files.filter((file) => file.selected);
  if (!selected.length) {
    log("沒有勾選檔案。");
    return;
  }
  const mode = el("convertMode").value;
  const summary = `即將轉換 ${selected.length} 個檔案\n模式：${mode}\n目標：${el("toEncoding").value}`;
  if (!confirm(summary)) return;

  el("convertButton").disabled = true;
  el("convertButton").textContent = "轉換中...";
  try {
    const data = await postJson("/api/convert", {
      root: state.root,
      files: selected.map((file) => file.path),
      fromEncoding: el("fromEncoding").value,
      toEncoding: el("toEncoding").value,
      mode,
      outputRoot: el("outputRoot").value,
      backupRoot: el("backupRoot").value,
    });
    log(
      [
        `轉換完成：成功 ${data.success}，失敗 ${data.failed}`,
        `Manifest: ${data.manifestPath}`,
        "",
        ...data.results.map((item) =>
          item.status === "success"
            ? `OK  ${item.path} -> ${item.destination}`
            : `ERR ${item.path}: ${item.error}`
        ),
      ].join("\n")
    );
  } catch (error) {
    log(`轉換失敗：${error.message}`);
  } finally {
    el("convertButton").disabled = false;
    el("convertButton").textContent = "轉換勾選檔案";
  }
}

el("scanButton").addEventListener("click", scan);
el("convertButton").addEventListener("click", convertSelected);
el("chooseRootButton").addEventListener("click", openDirectoryDialog);
el("closeDirectoryDialog").addEventListener("click", () => el("directoryDialog").close());
el("driveListButton").addEventListener("click", () => browseDirectories(""));
el("parentDirectoryButton").addEventListener("click", () => browseDirectories(state.browseParent));
el("applyDirectoryButton").addEventListener("click", () => {
  if (state.browsePath) el("rootInput").value = state.browsePath;
  el("directoryDialog").close();
});

el("directoryList").addEventListener("click", async (event) => {
  const item = event.target.closest(".directory-item");
  if (!item) return;
  await browseDirectories(item.dataset.path);
});

el("fileRows").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-preview]");
  if (button) preview(Number(button.dataset.preview));
});

el("fileRows").addEventListener("change", (event) => {
  const checkbox = event.target.closest(".file-check");
  if (!checkbox) return;
  const file = state.files[Number(checkbox.dataset.id)];
  if (file) file.selected = checkbox.checked;
});

el("selectAll").addEventListener("change", (event) => {
  const checked = event.target.checked;
  state.files.filter(matchesFilter).forEach((file) => {
    if (file.selectable) file.selected = checked;
  });
  renderRows();
});

document.querySelectorAll(".filters button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".filters button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.filter = button.dataset.filter;
    renderRows();
  });
});

renderStats();
