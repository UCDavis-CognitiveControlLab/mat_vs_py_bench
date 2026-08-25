function saveResult(name, raw, meta)
% Write results next to the Python arm's, in the same shapes:
% a JSON summary for the slide, and raw samples for re-analysis.
% Rig time is expensive -- never discard raw samples.
    outdir = fullfile(fileparts(fileparts(mfilename('fullpath'))), 'results');
    if ~exist(outdir, 'dir'), mkdir(outdir); end
    stamp = datestr(datetime('now','TimeZone','UTC'), 'yyyymmddTHHMMSSZ');
    base  = fullfile(outdir, sprintf('%s_%s', name, stamp));

    x = raw(isfinite(raw));
    s = struct('test', name, 'utc', stamp, 'meta', meta, 'stats', struct( ...
        'n', numel(x), 'median', median(x), 'mean', mean(x), 'sd', std(x), ...
        'iqr', iqr(x), 'p01', prctile(x,1), 'p99', prctile(x,99), ...
        'min', min(x), 'max', max(x)));

    fid = fopen([base '.json'], 'w');
    fwrite(fid, jsonencode(s, 'PrettyPrint', true));
    fclose(fid);
    writematrix(raw, [base '.csv']);   % CSV not .mat: open formats only

    fprintf('  -> %s.json\n', base);
end
