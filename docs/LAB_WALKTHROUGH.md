# Cách hoàn thành Lab 25B

Ngày thực hiện: 13/10/2026. Tài liệu này mô tả cách triển khai, kiểm chứng và tái tạo kết quả A–G. Báo cáo theo rubric: [REPORT.md](../reports/REPORT.md). Báo cáo A–C trước đó được giữ làm lịch sử: [REPORT_ABC.md](../reports/REPORT_ABC.md).

## 1. Xác định phạm vi và bảo vệ starter

Đọc README.md, docs/RUBRIC.md, report template, contract simulator và tests trước khi sửa. Kiểm tra `git status --short`; giữ nguyên các thay đổi A–C đã có. Không sửa simulator, tests có sẵn, naive client/executor, workflow services/runner, SLO data/scoring hoặc scenario YAML. Không gọi LLM thật hoặc dùng API key. Sau triển khai, bàn giao bằng commit riêng từng phần theo yêu cầu người dùng.

Chỉ sửa các implementation TODO, khối client/cache được phép, thêm test riêng và script kiểm chứng. Mọi thuật toán runtime nhận thời gian ảo `now`, không dùng time.sleep/time.time, không đọc state nội bộ simulator, không hard-code thời gian/tên băng trong client/cache.

## 2. Triển khai A–C

1. `errors.py`: phân loại timeout, rate limit, hết quota, overload, server error và lỗi client; tách retryability, breaker health và lợi ích failover.
2. `retry.py`: full-jitter exponential backoff có cap; retry-after cộng jitter; token bucket nhận ratio token cho mỗi logical request, refill theo thời gian và tiêu một token cho retry.
3. `breaker.py`: lưu cửa sổ kết quả gần nhất, trip theo failure/slow rate sau min_calls. Dùng Permit có generation để bỏ kết quả cũ; HALF_OPEN có giới hạn probe đang bay và yêu cầu đủ probe nhanh thành công.
4. `client.py`: ladder lọc tool capability, cooldown shared, retries riêng mỗi provider, kiểm tra deadline, failover và release permit khi cancel/lỗi không phản ánh health.
5. Chạy tests và naive/resilient compare. Thử timeout 8/budget 0.1/refill 0.5 so với timeout 5/budget 0.05/refill 0.1 trên ba seed; chọn gói cuối vì G2 p95 và G3 retry ratio tốt hơn.

Kết quả A–C: 45 test gốc PASS; 6 băng ×3 seed public PASS; thêm 18 lượt dịch cửa sổ +17 giây PASS. Script [validate_abc.py](../scripts/validate_abc.py) chỉ thay bản sao cấu hình trong bộ nhớ.

## 3. Triển khai D: workflow đúng một lần về hiệu ứng

File [executor.py](../src/gameday_lab/workflows/executor.py).

1. Tạo key ổn định bằng JSON tuple `(session_id, step)`; prefix riêng cho effect và checkpoint. Không sinh UUID mới cho mỗi attempt.
2. `_retry` chỉ bắt ServiceError và ServiceTimeout, tối đa max_attempts, hết lượt thì re-raise. WorkerCrash phải thoát để runner khởi động worker mới.
3. Đi theo STEPS. Nếu checkpoint có thì tải kết quả; nếu chưa có thì chạy step rồi mới ghi checkpoint.
4. Payment/email retry dùng cùng idempotency key. Crash sau khi chuyển tiền nhưng trước checkpoint được giải quyết bằng dedup phía service; resume không tính lại các step đã lưu.

Chạy 500 session seed 25: 0 duplicate refund/email, 0 lost refund, completion 100%, wasted LLM/crash 0.303; naive là 128 refund trùng và 81 email trùng. Grader xác nhận workflow PASS seed 25/26/27.

## 4. Triển khai E: alert theo tốc độ tiêu budget

File [alerting.py](../src/gameday_lab/slo/alerting.py).

1. Dựng prefix sums cho total và bad; tổng cửa sổ = prefix[end+1] − prefix[start].
2. Burn rate = bad/total/(1−SLO), trả 0 khi cửa sổ không có request.
3. Với mỗi rule, quét từng phút, yêu cầu cả long và short window vượt ngưỡng; gộp phút firing liên tục thành AlertEvent với end exclusive.
4. Tính budget từ tổng request có trọng số; dùng số chưa làm tròn cho quyết định freeze, chỉ làm tròn đầu ra. Thêm xử lý gần bằng ở ngưỡng để tránh lỗi số thực khi budget vừa cạn.

Public SLI: 3 page, 1 ticket, 0 false page; đã dùng 42.95% budget, còn 57.05%, không freeze. Hidden SLO chưa có dữ liệu nên không tạo dữ liệu giả hoặc tự nhận 4 điểm còn thiếu.

## 5. Triển khai G: semantic cache và stale-if-error

File [cache.py](../src/gameday_lab/cache.py).

1. Từ chối personal request khi lookup/store, và từ chối answer khác prompt_version của request.
2. Loại entry hết TTL + stale window; chỉ so cosine trong cùng prompt scope, chọn similarity cao nhất.
3. Store refresh entry tương tự, cập nhật thời gian và eviction LRU khi vượt max_entries.
4. CachingClient trả fresh hit ngay. Miss gọi inner client; success thông báo breaker trước rồi lưu answer.
5. Chỉ khi inner GiveUp mới lookup lại để phục vụ stale. Webhook invalidate theo source, kể cả entry stale.

Starter cache 0.80/600/0 qua unit tests nhưng C1 có 181 wrong answer và 80 outdated. Sweep threshold 0.90/0.92/0.94/0.95/0.97 với TTL 30 và stale 300 trên ba seed: nhóm 0.90–0.95 có cùng metric trên public; chọn 0.94 làm giá trị nghiêm vừa đủ trong phạm vi đã kiểm chứng, không tuyên bố tối ưu. 0.97 làm hit seed 25 xuống 0.499. Giá trị cuối: threshold 0.94, TTL 30, stale 300, max_entries 500.

C1 cuối seed 25: FAQ availability 0.9645, hit 0.590, stale 196, wrong 0, outdated 2. C1 PASS cả ba seed. Không có cache chỉ đạt FAQ availability 0.8424.

## 6. Thí nghiệm và postmortem F

[run_experiments.py](../scripts/run_experiments.py) tái tạo các ablation trong template: breaker hỏng với budget bật/tắt; timeout 5/30; bỏ tool filtering bằng subclass chỉ dùng trong experiment; cache starter/final, threshold 0.80/0.94/0.97, TTL 30/60/300 và tắt stale. Nó lưu metric/check vào `reports/experiments.json`; một số ablation cố ý FAIL, không phải lỗi của cấu hình cuối.

Giữ nguyên production code khi làm ablation. Từ CSV naive G2, tính attempts/s và success ratio trên cửa sổ 10 giây cho ít nhất năm mốc. Phân biệt trigger mất GPU với root cause retry nhiều tầng, và giải thích request đã timeout vẫn làm việc phía server. Tính ảnh hưởng theo số lượt thất bại thật; nêu rõ giả định volume cho budget tháng. Viết action items có owner theo vai trò và tiêu chí kiểm chứng, không quy lỗi cá nhân.

Chạy plot script có sẵn rồi xem PNG trực tiếp để kiểm tra nhãn, legend và hai client. Matplotlib được cài bổ sung vào `.venv` để vẽ; dependency runtime của lab vẫn là PyYAML. Bảng và nội dung đủ tám mục của template nằm ở `reports/REPORT.md`.

## 7. Chạy lại trên PowerShell

Từ thư mục gốc repository. Dùng lệnh Python trực tiếp tương đương Makefile; không cần có make.

```powershell
# Thiết lập lần đầu trên máy mới
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev,plot]"

# Tests gốc và tests biên riêng
.venv/Scripts/python.exe -m pytest tests validation -q

# So sánh clients, workflow, alerting và cache
.venv/Scripts/python.exe scripts/run_gameday.py --client both
.venv/Scripts/python.exe scripts/run_workflows.py --executor both
.venv/Scripts/python.exe scripts/run_slo.py --alerter both
.venv/Scripts/python.exe scripts/run_gameday.py --scenarios configs/scenarios_cache.yaml --client resilient,cached --out reports/cache

# Thí nghiệm và kiểm tra không phụ thuộc thời điểm cố định
.venv/Scripts/python.exe scripts/run_experiments.py
.venv/Scripts/python.exe scripts/validate_abc.py --seeds 25,26,27 --shift-s 17

# Vẽ hình, đặt font cache trong workspace
$env:MPLCONFIGDIR = Join-Path $PWD 'reports/gameday/.mplconfig'
.venv/Scripts/python.exe scripts/plot_timeseries.py --scenario G2_overload_storm

# Chấm tự động trên ba seed public
.venv/Scripts/python.exe scripts/grade.py --seeds 25,26,27
git diff --check
```

Lệnh thiết lập máy mới được cung cấp để tái tạo; phiên này dùng `.venv` có sẵn và chỉ cài thêm matplotlib. Chưa chạy cài đặt hoàn toàn sạch trên máy khác. `MPLCONFIGDIR` giúp tránh cảnh báo không ghi được font cache ở profile Windows; không liên quan logic simulator.

## 8. Kết quả và file bàn giao

| Kiểm tra | Kết quả |
|---|---|
| Test gốc | 82/82 PASS |
| Test bổ sung trong validation/ | 11/11 PASS |
| Game Day G1–G6 ×3 seed | 18/18 PASS |
| A–C dịch cửa sổ +17 giây ×3 seed | 18/18 PASS |
| Workflow 500 session ×3 seed | PASS mọi check |
| Public SLO | PASS, false_pages=0 |
| C1 cache ×3 seed | 3/3 PASS |
| Grader | 84/88; 4 điểm hidden SLO chưa chấm |
| Ruff trên các file triển khai/script/test bổ sung | PASS |
| git diff --check | PASS |

| File | Vai trò |
|---|---|
| src/gameday_lab/errors.py, retry.py, breaker.py, client.py | A–C |
| src/gameday_lab/workflows/executor.py | D |
| src/gameday_lab/slo/alerting.py | E |
| src/gameday_lab/cache.py | G |
| configs/gameday.yaml | Client/cache settings |
| validation/test_abc_edges.py, test_remaining_edges.py | Test biên, không sửa tests gốc |
| scripts/validate_abc.py, run_experiments.py | Kiểm chứng và ablation lặp được |
| reports/REPORT.md | Bài report F đủ tám mục |
| docs/LAB_WALKTHROUGH.md | Tài liệu cách thực hiện này |
| reports/scoreboard.json | Điểm, checks từng seed |
| reports/experiments.json | Kết quả các ablation |
| reports/workflows.json, slo.json | So sánh workflow/alerting |
| reports/gameday/, reports/cache/ | Metrics, CSV và hình G2 |

`.gitignore` có sẵn bỏ qua JSON, PNG và các thư mục artifact trên. Khi bàn giao theo yêu cầu commit/push từng phần, các artifact kiểm chứng được thêm bằng allowlist `git add -f` vào commit tương ứng; không thay ignore rules. Font cache, virtualenv và file tạm không nằm trong bản nộp. Xem `git log --oneline` để đối chiếu các commit Part A–G. Báo cáo A–C được giữ như ghi nhận lịch sử trước khi bàn giao.

## 9. Giới hạn

Không có băng ẩn C/G và hidden SLO, nên kết quả chỉ chứng minh public và biến thể cục bộ đã chạy. Report 12 điểm vẫn cần chấm tay. Cache không thay thế nguồn dữ liệu cá nhân trực tiếp và không cứu tool workflow khi mọi provider hỏng. CI drill bổ sung, dashboard observability và deployment production chỉ là hướng phát triển, chưa được triển khai hoặc xác nhận.
