# Báo cáo Part A–C — Lab 25B

Ngày 13/10/2026. Phạm vi theo README.md và docs/RUBRIC.md: chỉ hoàn thành A–C. D, E, G và postmortem đầy đủ Part F chưa thuộc phạm vi yêu cầu này.

## 1. Kết quả kiểm chứng

- 45/45 test có sẵn PASS: A 21, B 13, C 11.
- 6/6 test biên bổ sung PASS, tổng 51 test.
- 18/18 lượt chạy public PASS: 6 băng × seed 25, 26, 27.
- 18/18 lượt chạy dịch toàn bộ cửa sổ sự cố +17 giây PASS. Script chỉ thay bản sao trong bộ nhớ, không sửa scenario YAML.
- Không sửa simulator, naive client, tests có sẵn hoặc các file bị cấm khác.
- Kết quả public và biến thể cục bộ không bảo đảm điểm trên băng ẩn của giảng viên.

## 2. Game Day: naive và resilient (seed 25)

| Băng | Client | availability | p95 (s) | amplification | retry_ratio | cost/turn | recovery (s) | PASS |
|---|---|---:|---:|---:|---:|---:|---:|:---:|
| G1 | naive | 0.7194 | 7.157 | 7.738 | 6.738 | 2.163 | 4 | FAIL |
| G1 | resilient | 1.0000 | 4.809 | 1.065 | 0.002 | 2.107 | 0 | PASS |
| G2 | naive | 0.4560 | 15.034 | 9.904 | 8.904 | 4.627 | 155 | FAIL |
| G2 | resilient | 1.0000 | 6.256 | 1.041 | 0.008 | 2.124 | 0 | PASS |
| G3 | naive | 1.0000 | 4.768 | 1.164 | 0.164 | 2.328 | 0 | FAIL |
| G3 | resilient | 1.0000 | 4.612 | 1.054 | 0.025 | 2.127 | 0 | PASS |
| G4 | naive | 1.0000 | 13.764 | 1.004 | 0.004 | 2.008 | 0 | FAIL |
| G4 | resilient | 1.0000 | 5.481 | 1.035 | 0.004 | 2.115 | 0 | PASS |
| G5 | naive | 0.3699 | 5.359 | 17.030 | 16.030 | 2.124 | N/A | FAIL |
| G5 | resilient | 0.8179 | 5.471 | 1.004 | 0.003 | 2.505 | N/A | PASS |
| G6 | naive | 0.5170 | 4.836 | 12.344 | 11.344 | 2.009 | 0 | FAIL |
| G6 | resilient | 1.0000 | 6.413 | 1.065 | 0.026 | 2.188 | 0 | PASS |

Recovery là metric trên toàn bộ call, bao gồm fallback. Giá trị 0 không có nghĩa primary chưa từng lỗi. G5 không có mốc restore nên recovery là N/A.

## 3. Cấu hình và lý do

Đã thử starter và cấu hình cuối trên cùng ba seed. Thay timeout và budget cùng lúc; số trước/sau thể hiện hiệu quả của cả gói cấu hình, không tách riêng quan hệ nhân quả cho từng tham số.

| Tham số | Giá trị cuối | Lý do và bằng chứng |
|---|---:|---|
| attempt_timeout_s | 5.0 | Giảm thời gian mắc kẹt trước fallback. G2 p95 starter → cuối: seed 25: 10.023 → 6.256; seed 26: 11.397 → 8.250; seed 27: 9.789 → 5.025 giây. |
| max_attempts_per_provider | 2 | Tối đa một retry transient mỗi provider; G2 amplification 1.041 ở seed 25, dưới 1.6. |
| min_time_left_s | 1.0 | Không cấp attempt với timeout dưới 1 giây; test deadline và giải phóng probe PASS. |
| backoff_base_s / cap_s | 0.25 / 4.0 | Full jitter có giới hạn; retry-after là thời gian tối thiểu cộng jitter. G1 có 0 vi phạm retry-after ở seed 25. |
| retry_budget_ratio / min_per_s / max_tokens | 0.05 / 0.1 / 20 | G3 retry_ratio starter → cuối: 0.049 → 0.025, 0.030 → 0.021, 0.030 → 0.022 trên ba seed. Không phải trần tuyệt đối 5% vì còn token ban đầu và refill theo thời gian. |
| quota_cooldown_s | 300 | Tránh gọi lại account hết quota. G5 availability 0.8179, client_error_retries = 0. |
| breaker.window_size / min_calls | 20 / 10 | Cửa sổ gần nhất không trip chỉ vì vài mẫu. G2 recovery và primary_share_after_restore đạt mọi check trên ba seed. |
| breaker.failure_rate_threshold | 0.5 | Trip khi ít nhất một nửa kết quả lỗi. G3 availability vẫn 1.0 ở seed 25 với retry_ratio 0.025. |
| breaker.slow_call_s / slow_rate_threshold | 5.0 / 0.6 | Có ghi nhận thành công chậm; test slow-success và slow-probe PASS. Với timeout cũng là 5 giây, call lâu hơn thường thành timeout và góp vào failure rate. G4 p95 5.481 giây, dưới 10. |
| breaker.open_duration_s | 10.0 | Probe định kỳ để quay lại primary; các check recovery/primary share G2 và G4 PASS trên ba seed. |
| breaker.half_open_max_probes / successes | 2 / 2 | Giới hạn hai probe đang bay, đóng sau hai probe nhanh thành công; test giới hạn probe, lỗi/chậm, generation cũ và cancel PASS. |

Giữ các tham số breaker của starter sau kiểm chứng; không kết luận chúng tối ưu từ các băng public.

## 4. Quyết định xử lý lỗi

| Loại lỗi | Breaker | Retry cùng provider | Cooldown / fallback |
|---|---|---|---|
| CLIENT_ERROR | release, không ghi health | Không | GiveUp ngay; không failover request sai |
| QUOTA_EXHAUSTED | release | Không | Cooldown 300 giây; failover ngay, không chờ quota |
| RATE_LIMITED | release | Không retry ngay | Cooldown dùng chung đến retry-after; failover ngay; chỉ chờ cooldown ≤5 giây khi hết lựa chọn và đủ deadline |
| OVERLOADED / SERVER_ERROR / TIMEOUT | ghi failure | Khi còn attempt, budget, breaker cho phép và đủ deadline | Nếu không retry được, chuyển provider kế tiếp |

Ladder giữ thứ tự cấu hình nhưng loại provider không hỗ trợ tool khỏi task tool. `tries` đếm riêng theo provider. Mỗi call mới bắt đầu lại từ primary. Thành công cập nhật latency; cancel trả permit; generation cũ không tác động tới state mới. Retry budget dùng chung cho toàn client và chỉ ghi request một lần khi bắt đầu logical call.

## 5. Chạy lại và artifact

Chạy từ thư mục gốc trên PowerShell:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_errors_retry.py tests/test_breaker.py tests/test_client.py validation/test_abc_edges.py -q
.venv/Scripts/python.exe scripts/run_gameday.py --client both
.venv/Scripts/python.exe scripts/validate_abc.py --seeds 25,26,27 --shift-s 17
```

- `reports/gameday/naive.json`, `resilient.json` và 12 CSV: kết quả seed 25.
- `reports/abc_validation.json`: metrics và checks cho 36 lượt chạy.
- `reports/abc_tuning.json`: 36 lượt chạy starter/cấu hình cuối, 18 mỗi cấu hình. Starter dùng timeout 8, budget ratio 0.1, refill 0.5; phần còn lại giống cấu hình cuối. Có thể tái tạo bằng override ba tham số trong bản sao LabConfig rồi chạy cùng seed.
- JSON và thư mục gameday bị ignore theo `.gitignore` có sẵn; report này lưu các số chính để review trong Git.
- `validation/test_abc_edges.py`: kiểm tra chờ retry-after khi mọi provider rate limit, không chờ quota, hết budget, deadline không rò probe, kết quả cũ và số retry rất lớn.

## 6. Giới hạn còn lại

G2 seed 26 vẫn có p95 8.250 giây: request đã vào hàng đợi trước lúc breaker trip phải chờ timeout hoặc hoàn thành. G6 seed 25 p95 tăng từ 6.096 lên 6.413 khi đổi cấu hình dù cả hai đều PASS. Timeout ngắn có thể bỏ request hợp lệ chậm, tạo công việc thừa phía server và tăng chi phí. Khi mọi provider hỏng thì không bảo đảm availability; cache/stale-if-error thuộc Part G chưa triển khai trong yêu cầu A–C.
