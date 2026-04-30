/* Setup Wizard JS */
var current = 0;
var totalSteps = 7;
var steps = document.querySelectorAll('.step');
var dots = document.querySelectorAll('.progress-step');
var fill = document.getElementById('progressFill');
var uploadedLogoUrl = '';
var importedFile = null;
var detectedHeaders = [];

function goStep(dir) {
    var next = current + dir;
    if (next < 0) return;
    if (next >= totalSteps) {
        saveToLocalStorage();
        document.getElementById('setupForm').submit();
        return;
    }
    current = next;
    renderStep();
}

function renderStep() {
    steps.forEach(function(s, i) { s.classList.toggle('active', i === current); });
    dots.forEach(function(d, i) {
        d.classList.remove('active', 'done');
        if (i === current) d.classList.add('active');
        else if (i < current) d.classList.add('done');
    });
    fill.style.width = (current / (totalSteps - 1) * 100) + '%';

    var back = document.getElementById('btnBack');
    var skip = document.getElementById('btnSkip');
    var next = document.getElementById('btnNext');

    back.style.display = current > 0 ? '' : 'none';
    skip.style.display = (current > 0 && current < totalSteps - 1) ? '' : 'none';

    if (current === 0) next.textContent = 'Get Started';
    else if (current === totalSteps - 1) { next.textContent = 'Launch Counselor Assistant'; buildSummary(); }
    else next.textContent = 'Next';
}

/* ---- Password strength ---- */
var pwInput = document.getElementById('password');
var pwBar = document.getElementById('pwBar');
if (pwInput) {
    pwInput.addEventListener('input', function() {
        var v = this.value, s = 0;
        if (v.length >= 8) s++;
        if (v.length >= 12) s++;
        if (/[A-Z]/.test(v) && /[a-z]/.test(v)) s++;
        if (/\d/.test(v)) s++;
        if (/[^A-Za-z0-9]/.test(v)) s++;
        var pct = Math.min(s / 4 * 100, 100);
        var colors = ['#ef4444', '#f59e0b', '#eab308', '#22c55e', '#16a34a'];
        pwBar.style.width = pct + '%';
        pwBar.style.background = colors[Math.min(s, colors.length - 1)];
    });
}

/* ---- Color pickers ---- */
function syncColor(pickerId, textId) {
    var picker = document.getElementById(pickerId);
    var text = document.getElementById(textId);
    if (!picker || !text) return;
    picker.addEventListener('input', function() { text.value = this.value; });
    text.addEventListener('input', function() {
        if (/^#[0-9a-fA-F]{6}$/.test(this.value)) picker.value = this.value;
    });
}
syncColor('primary_color_picker', 'primary_color');
syncColor('secondary_color_picker', 'secondary_color');

/* ---- Emoji picker ---- */
document.querySelectorAll('.emoji-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
        document.querySelectorAll('.emoji-btn').forEach(function(b) { b.classList.remove('selected'); });
        this.classList.add('selected');
        document.getElementById('mascotEmoji').value = this.dataset.emoji;
    });
});

/* ---- Logo upload ---- */
var logoDrop = document.getElementById('logoDrop');
var logoFile = document.getElementById('logoFile');

['dragenter','dragover'].forEach(function(ev) {
    logoDrop.addEventListener(ev, function(e) { e.preventDefault(); logoDrop.classList.add('dragover'); });
});
['dragleave','drop'].forEach(function(ev) {
    logoDrop.addEventListener(ev, function(e) { e.preventDefault(); logoDrop.classList.remove('dragover'); });
});
logoDrop.addEventListener('drop', function(e) {
    if (e.dataTransfer.files.length) {
        logoFile.files = e.dataTransfer.files;
        handleLogoUpload(e.dataTransfer.files[0]);
    }
});
logoFile.addEventListener('change', function() {
    if (this.files.length) handleLogoUpload(this.files[0]);
});

function handleLogoUpload(file) {
    if (file.size > 2 * 1024 * 1024) { alert('Logo must be under 2MB.'); return; }
    var fd = new FormData();
    fd.append('logo', file);
    fetch('/setup/upload-logo', { method: 'POST', body: fd })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.ok) {
                uploadedLogoUrl = d.logoUrl;
                document.getElementById('logoImg').src = d.logoUrl + '?v=' + Date.now();
                document.getElementById('logoPreview').style.display = '';
                document.getElementById('logoPrompt').style.display = 'none';
                document.getElementById('removeLogo').style.display = '';
            } else { alert(d.error || 'Upload failed.'); }
        })
        .catch(function() { alert('Upload failed.'); });
}

function removeLogo() {
    uploadedLogoUrl = '';
    document.getElementById('logoPreview').style.display = 'none';
    document.getElementById('logoPrompt').style.display = '';
    document.getElementById('removeLogo').style.display = 'none';
}

/* ---- Student file drop / upload ---- */
var fileDrop = document.getElementById('fileDrop');
var csvFile = document.getElementById('csvFile');
var fileInfo = document.getElementById('fileInfo');

['dragenter','dragover'].forEach(function(ev) {
    fileDrop.addEventListener(ev, function(e) { e.preventDefault(); fileDrop.classList.add('dragover'); });
});
['dragleave','drop'].forEach(function(ev) {
    fileDrop.addEventListener(ev, function(e) { e.preventDefault(); fileDrop.classList.remove('dragover'); });
});
fileDrop.addEventListener('drop', function(e) {
    if (e.dataTransfer.files.length) {
        csvFile.files = e.dataTransfer.files;
        handleStudentFile(e.dataTransfer.files[0]);
    }
});
csvFile.addEventListener('change', function() {
    if (this.files.length) handleStudentFile(this.files[0]);
});

function handleStudentFile(file) {
    importedFile = file;
    fileInfo.textContent = 'Selected: ' + file.name + ' (' + (file.size / 1024).toFixed(1) + ' KB)';
    fileInfo.classList.add('show');

    var fd = new FormData();
    fd.append('file', file);
    fetch('/setup/import-preview', { method: 'POST', body: fd })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.ok) {
                detectedHeaders = d.headers;
                fileInfo.textContent = 'Selected: ' + file.name + ' — ' + d.row_count + ' students found';
                buildMappingGrid(d.headers);
                document.getElementById('importPreview').classList.add('show');
            }
        })
        .catch(function() {});
}

/* ---- Column mapping ---- */
var MAPPING_FIELDS = [
    { key: 'student_id', label: 'Student ID', patterns: ['student.*id', 'perm', 'id.*num', 'sis.*id'] },
    { key: 'first_name', label: 'First Name', patterns: ['first', 'fname', 'given'] },
    { key: 'last_name', label: 'Last Name', patterns: ['last', 'lname', 'surname', 'family'] },
    { key: 'grade_level', label: 'Grade Level', patterns: ['grade', 'gr\\.?\\s*lev', 'yr'] },
    { key: 'gender', label: 'Gender', patterns: ['gender', 'sex'] },
    { key: 'email', label: 'Email', patterns: ['email', 'e-mail'] },
    { key: 'ethnicity', label: 'Ethnicity', patterns: ['ethnic', 'race'] },
    { key: 'date_of_birth', label: 'Date of Birth', patterns: ['birth', 'dob', 'bday'] }
];

function buildMappingGrid(headers) {
    var grid = document.getElementById('mappingGrid');
    grid.innerHTML = '';
    MAPPING_FIELDS.forEach(function(field) {
        var div = document.createElement('div');
        var lbl = document.createElement('label');
        lbl.textContent = field.label;
        var sel = document.createElement('select');
        sel.id = 'map_' + field.key;
        sel.innerHTML = '<option value="">(skip)</option>';
        headers.forEach(function(h) {
            var opt = document.createElement('option');
            opt.value = h;
            opt.textContent = h;
            sel.appendChild(opt);
        });
        // Auto-detect
        var best = autoDetect(headers, field.patterns);
        if (best) sel.value = best;
        div.appendChild(lbl);
        div.appendChild(sel);
        grid.appendChild(div);
    });
}

function autoDetect(headers, patterns) {
    for (var i = 0; i < patterns.length; i++) {
        var re = new RegExp(patterns[i], 'i');
        for (var j = 0; j < headers.length; j++) {
            if (re.test(headers[j])) return headers[j];
        }
    }
    return '';
}

/* ---- Import students ---- */
function importStudents() {
    if (!importedFile) { alert('Please select a file first.'); return; }
    var mapping = {};
    MAPPING_FIELDS.forEach(function(field) {
        var sel = document.getElementById('map_' + field.key);
        if (sel && sel.value) mapping[field.key] = sel.value;
    });
    var fd = new FormData();
    fd.append('file', importedFile);
    fd.append('mapping', JSON.stringify(mapping));

    var btn = document.getElementById('importBtn');
    var result = document.getElementById('importResult');
    btn.disabled = true;
    btn.textContent = 'Importing...';
    result.textContent = '';

    fetch('/setup/import-students', { method: 'POST', body: fd })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            btn.disabled = false;
            btn.textContent = 'Import Students';
            if (d.ok) {
                result.innerHTML = '<span style="color:#16a34a;font-weight:600;">' + d.imported +
                    ' imported</span>' + (d.skipped ? ', ' + d.skipped + ' skipped' : '');
            } else {
                result.innerHTML = '<span style="color:#dc2626;">' + (d.error || 'Import failed') + '</span>';
            }
        })
        .catch(function() {
            btn.disabled = false;
            btn.textContent = 'Import Students';
            result.innerHTML = '<span style="color:#dc2626;">Network error</span>';
        });
}

/* ---- Ollama test ---- */
function testOllama() {
    var url = document.getElementById('ollama_url').value.trim() || 'http://localhost:11434';
    var status = document.getElementById('ollamaStatus');
    status.textContent = 'Testing...';
    status.style.color = '#6b7280';
    fetch(url + '/api/tags', { mode: 'cors' })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            var models = (d.models || []).map(function(m) { return m.name; });
            if (models.length) {
                status.innerHTML = '<span style="color:#16a34a;">Connected — ' + models.length + ' model(s): ' + models.slice(0,3).join(', ') + '</span>';
            } else {
                status.innerHTML = '<span style="color:#f59e0b;">Connected but no models found. Run: ollama pull gemma3:4b</span>';
            }
        })
        .catch(function() {
            status.innerHTML = '<span style="color:#dc2626;">Cannot connect. Is Ollama running?</span>';
        });
}

/* ---- Theme selection ---- */
function selectTheme(t) {
    document.querySelectorAll('.theme-pill').forEach(function(p) { p.classList.remove('active'); });
    document.querySelector('.theme-pill[data-theme="' + t + '"]').classList.add('active');
    document.getElementById('themeInput').value = t;
}

/* ---- Grade levels "All" toggle ---- */
document.querySelectorAll('input[name="grade_levels"]').forEach(function(cb) {
    cb.addEventListener('change', function() {
        if (this.value === 'all' && this.checked) {
            document.querySelectorAll('input[name="grade_levels"]').forEach(function(c) {
                if (c.value !== 'all') c.checked = true;
            });
        } else if (this.value !== 'all') {
            document.querySelector('input[name="grade_levels"][value="all"]').checked = false;
        }
    });
});

/* ---- Save school config to localStorage for course catalog ---- */
function saveToLocalStorage() {
    var cfg = {
        schoolName: gv('school_name'),
        shortName: gv('shortName'),
        mascotEmoji: document.getElementById('mascotEmoji').value,
        motto: gv('motto'),
        colors: { primary: gv('primary_color'), secondary: gv('secondary_color') },
        logoUrl: uploadedLogoUrl,
        contactPhone: gv('contact_phone'),
        contactEmail: gv('contact_email'),
        contactAddress: gv('contact_address'),
        setupComplete: true
    };
    try { localStorage.setItem('school_config', JSON.stringify(cfg)); } catch(e) {}
}

/* ---- Build finish summary ---- */
function buildSummary() {
    var items = [];
    function add(label, val, fallback) {
        if (val) items.push('<li><span class="check">&#10003;</span>' + label + ': <strong>' + esc(val) + '</strong></li>');
        else items.push('<li><span class="miss">&mdash;</span>' + label + ': <em>' + (fallback || 'Not set') + '</em></li>');
    }
    add('Name', gv('display_name'), 'School Counselor');
    add('School', gv('school_name'));
    add('Username', gv('username') || 'counselor');

    var pw = document.getElementById('password').value;
    if (pw.length >= 8) items.push('<li><span class="check">&#10003;</span>Password: <strong>Custom set</strong></li>');
    else items.push('<li><span class="miss">&mdash;</span>Password: <em>Default (changeme)</em></li>');

    var title = gv('counselor_title');
    if (title) add('Title', title);

    var pc = gv('primary_color');
    if (pc && pc !== '#2C5F8A') items.push('<li><span class="check">&#10003;</span>School colors: <span style="display:inline-block;width:12px;height:12px;border-radius:3px;background:' + esc(pc) + ';vertical-align:middle;"></span> <span style="display:inline-block;width:12px;height:12px;border-radius:3px;background:' + esc(gv('secondary_color')) + ';vertical-align:middle;margin-left:2px;"></span></li>');

    if (uploadedLogoUrl) items.push('<li><span class="check">&#10003;</span>School logo: <strong>Uploaded</strong></li>');

    var grades = [];
    document.querySelectorAll('input[name="grade_levels"]:checked').forEach(function(c) {
        if (c.value !== 'all') grades.push(c.value);
    });
    if (grades.length) add('Grade levels', grades.join(', '));

    var result = document.getElementById('importResult');
    if (result && result.textContent.indexOf('imported') > -1) {
        items.push('<li><span class="check">&#10003;</span>Students: <strong>' + result.textContent + '</strong></li>');
    }

    if (gv('ical_url')) items.push('<li><span class="check">&#10003;</span>Calendar: <strong>Connected</strong></li>');
    if (gv('ollama_url') !== 'http://localhost:11434' || gv('ollama_model') !== 'gemma3:4b') {
        items.push('<li><span class="check">&#10003;</span>AI: <strong>' + esc(gv('ollama_model')) + '</strong></li>');
    }

    var theme = document.getElementById('themeInput').value;
    items.push('<li><span class="check">&#10003;</span>Theme: <strong>' + esc(theme.charAt(0).toUpperCase() + theme.slice(1)) + '</strong></li>');

    document.getElementById('finishSummary').innerHTML = items.join('');
}

function gv(id) {
    var el = document.getElementById(id);
    return el ? el.value.trim() : '';
}

function esc(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

renderStep();
