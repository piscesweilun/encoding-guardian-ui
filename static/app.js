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

function isTargetDifferent(file) {
  const toEncoding = el("toEncoding").value;
  if (toEncoding === "utf-8") return file.encoding !== "utf-8";
  if (toEncoding === "utf-8-sig") return file.encoding !== "utf-8-sig";
  return file.encoding !== toEncoding;
}

function getFromEncoding() {
  const selected = el("fromEncoding").value;
  if (selected !== "custom") return selected;
  return el("customFromEncoding").value.trim();
}

function canSelectFile(file) {
  return isTargetDifferent(file);
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
      return canSelectFile(file);
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
  const labels = new Map([
    ["utf-8", "UTF-8"],
    ["utf-8-sig", "UTF-8 with BOM"],
    ["cp950", "CP950 / Big5"],
    ["utf-16-le", "UTF-16 LE"],
    ["utf-16-be", "UTF-16 BE"],
    ["utf-32-le", "UTF-32 LE"],
    ["utf-32-be", "UTF-32 BE"],
    ["gb18030", "GB18030"],
    ["gbk", "GBK"],
    ["shift_jis", "Shift_JIS"],
    ["cp932", "CP932"],
    ["euc_jp", "EUC-JP"],
    ["euc_kr", "EUC-KR"],
    ["cp1252", "Windows-1252"],
    ["latin_1", "Latin-1"],
    ["unknown", "Unknown"],
    ["binary", "Binary"],
  ]);
  const entries = [...labels.entries()];
  for (const key of Object.keys(counts)) {
    if (!labels.has(key)) entries.push([key, key]);
  }
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
      const canSelect = canSelectFile(file);
      return `
        <tr>
          <td><input class="file-check" type="checkbox" data-id="${id}" ${file.selected ? "checked" : ""} ${canSelect ? "" : "disabled"} /></td>
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
      selected: canSelectFile(file),
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
  const fromEncoding = getFromEncoding();
  if (!fromEncoding) {
    el("previewText").textContent = "請輸入自訂來源編碼。";
    return;
  }
  el("previewMeta").textContent = file.relative_path;
  el("previewText").textContent = "讀取預覽中...";
  try {
    const data = await postJson("/api/preview", {
      path: file.path,
      fromEncoding,
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
  const fromEncoding = getFromEncoding();
  if (!fromEncoding) {
    log("請輸入自訂來源編碼。");
    return;
  }
  const selected = state.files.filter((file) => file.selected);
  if (!selected.length) {
    log("沒有勾選檔案。");
    return;
  }
  if (fromEncoding === "auto" && selected.some((file) => ["binary", "unknown"].includes(file.encoding))) {
    log("有檔案無法自動判斷來源編碼。請把來源編碼改成 UTF-16 LE 或正確的編碼後再轉換。");
    return;
  }
  const mode = el("convertMode").value;
  const modeText =
    mode === "in-place"
      ? `原地轉換並備份\n備份目錄：${el("backupRoot").value}`
      : `輸出到新目錄，原始檔不會變\n輸出目錄：${el("outputRoot").value}`;
  const summary = `即將轉換 ${selected.length} 個檔案\n來源：${fromEncoding}\n目標：${el("toEncoding").value}\n模式：${modeText}`;
  if (!confirm(summary)) return;

  el("convertButton").disabled = true;
  el("convertButton").textContent = "轉換中...";
  try {
    const data = await postJson("/api/convert", {
      root: state.root,
      files: selected.map((file) => file.path),
      fromEncoding,
      toEncoding: el("toEncoding").value,
      mode,
      outputRoot: el("outputRoot").value,
      backupRoot: el("backupRoot").value,
    });
    log(
      [
        `轉換完成：成功 ${data.success}，失敗 ${data.failed}`,
        mode === "in-place" ? "原始檔已更新；備份已建立。" : "原始檔未修改；請到輸出目錄查看轉換後檔案。",
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
    if (canSelectFile(file)) file.selected = checked;
  });
  renderRows();
});

function refreshSourceEncodingControls() {
  el("customFromEncodingLabel").hidden = el("fromEncoding").value !== "custom";
  state.files.forEach((file) => {
    if (!canSelectFile(file)) file.selected = false;
  });
  renderRows();
}

el("fromEncoding").addEventListener("change", refreshSourceEncodingControls);
el("customFromEncoding").addEventListener("input", refreshSourceEncodingControls);
el("toEncoding").addEventListener("change", () => {
  state.files.forEach((file) => {
    file.selected = canSelectFile(file);
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
