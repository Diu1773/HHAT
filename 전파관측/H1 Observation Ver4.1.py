import os
import sys
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
import ast

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in os.environ['PATH']:
    os.environ['PATH'] = current_dir + os.pathsep + os.environ['PATH']
if sys.platform == 'win32':
    os.add_dll_directory(current_dir)

try:
    from rtlsdr import RtlSdr
    print("성공: RtlSdr 라이브러리를 불러왔습니다.")
except ImportError:
    print("실패: pyrtlsdr 패키지나 드라이버를 확인하세요.")
    sys.exit()

# --- 천문 데이터 처리를 위한 astropy 추가 ---
try:
    from astropy.io import fits
except ImportError:
    print("astropy 라이브러리가 필요합니다. 'pip install astropy'를 확인하세요.")

class HIScopeGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("HI-Observation System v4.1")
        self.root.geometry("450x700")
        self.is_testing = False

        # --- 기본 파라미터 설정 ---
        self.sample_rate = tk.StringVar(value="2.4e6")
        self.center_freq = tk.StringVar(value="1420.4e6")
        self.gain = tk.StringVar(value="40.0")
        self.nfft = tk.StringVar(value="2048")
        self.iterations = tk.StringVar(value="5000")
        self.samples_per_scan = tk.StringVar(value="512*1024")
        self.save_path = tk.StringVar(value=os.getcwd())
        self.baseline_fits_path = tk.StringVar(value="Not Selected")
        
        self.use_bias_tee = tk.BooleanVar(value=False)
        self.remove_dc = tk.BooleanVar(value=True)
        self.use_hanning = tk.BooleanVar(value=True)
        self.remove_baseline = tk.BooleanVar(value=False)

        self.create_widgets()
        self.check_sdr_connection()

    def evaluate_expr(self, expr_str):
        try:
            node = ast.parse(expr_str, mode='eval')
            return float(eval(compile(node, '<string>', 'eval')))
        except: return None

    def create_widgets(self):
        status_frame = tk.Frame(self.root, pady=5); status_frame.pack(fill="x", padx=15)
        self.status_label = tk.Label(status_frame, text="SDR 상태: 확인 중...", font=("Arial", 9, "bold"))
        self.status_label.pack(side="left", padx=5)
        tk.Button(status_frame, text="↻", command=self.check_sdr_connection, width=3).pack(side="left", padx=5)

        input_frame = tk.LabelFrame(self.root, text=" Parameters ", padx=10, pady=10)
        input_frame.pack(fill="x", padx=15, pady=5)
        
        tk.Label(input_frame, text="Gain (dB):").grid(row=2, column=0, sticky="w", pady=4)
        tk.Entry(input_frame, textvariable=self.gain).grid(row=2, column=1, sticky="ew", padx=8)
        self.test_btn = tk.Button(input_frame, text="Gain Test", command=self.toggle_test_mode, bg="orange", width=10)
        self.test_btn.grid(row=2, column=2, padx=2)

        fields = [("Sample Rate:", self.sample_rate, 0), ("Center Freq:", self.center_freq, 1),
                  ("NFFT Size:", self.nfft, 3), ("Iterations:", self.iterations, 4),
                  ("Samples/Scan:", self.samples_per_scan, 5)]
        for label, var, row in fields:
            tk.Label(input_frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
            tk.Entry(input_frame, textvariable=var).grid(row=row, column=1, columnspan=2, sticky="ew", padx=8)
        input_frame.columnconfigure(1, weight=1)

        opt_frame = tk.LabelFrame(self.root, text=" Options ", padx=10, pady=5)
        opt_frame.pack(fill="x", padx=15, pady=5)
        tk.Checkbutton(opt_frame, text="Enable Bias-Tee (LNA)", variable=self.use_bias_tee).pack(anchor="w")
        tk.Checkbutton(opt_frame, text="Remove DC Spike", variable=self.remove_dc).pack(anchor="w")
        tk.Checkbutton(opt_frame, text="Apply Hanning Window", variable=self.use_hanning).pack(anchor="w")
        tk.Checkbutton(opt_frame, text="Subtract Baseline (Calibration)", variable=self.remove_baseline).pack(anchor="w")

        path_frame = tk.LabelFrame(self.root, text=" File & Baseline Path ", padx=10, pady=5)
        path_frame.pack(fill="x", padx=15, pady=5)
        
        tk.Label(path_frame, text="Save Directory:").pack(anchor="w")
        tk.Entry(path_frame, textvariable=self.save_path, state="readonly", fg="blue").pack(fill="x", padx=2, pady=2)
        tk.Button(path_frame, text="Set Save Folder", command=self.browse_folder).pack(fill="x", pady=2)
        
        tk.Label(path_frame, text="Baseline FITS File:").pack(anchor="w", pady=(5,0))
        tk.Entry(path_frame, textvariable=self.baseline_fits_path, state="readonly", fg="red").pack(fill="x", padx=2, pady=2)
        
        btn_box = tk.Frame(path_frame)
        btn_box.pack(fill="x", pady=2)
        tk.Button(btn_box, text="Load Baseline FITS", command=self.browse_baseline).pack(side="left", expand=True, fill="x", padx=(0,2))
        tk.Button(btn_box, text="Reset", command=self.reset_baseline, bg="#ffcccc", width=8).pack(side="left")

        self.run_btn = tk.Button(self.root, text="START OBSERVATION", bg="gray", fg="white", 
                                 font=("Arial", 11, "bold"), height=2, command=self.run_observation, state="disabled")
        self.run_btn.pack(fill="x", padx=15, pady=20)

    def check_sdr_connection(self):
        try:
            s = RtlSdr(); s.close()
            self.status_label.config(text="SDR 상태: 연결됨", fg="green"); self.run_btn.config(state="normal", bg="red")
        except:
            self.status_label.config(text="SDR 상태: 연결 안 됨", fg="red"); self.run_btn.config(state="disabled", bg="gray")

    def toggle_test_mode(self):
        if self.is_testing: self.is_testing = False
        else: self.is_testing = True; self.run_live_test()

    def run_live_test(self):
        self.test_btn.config(text="STOP Test", bg="red")
        try:
            sdr = RtlSdr()
            sdr.sample_rate = self.evaluate_expr(self.sample_rate.get())
            sdr.center_freq = self.evaluate_expr(self.center_freq.get())
            plt.ion(); fig, ax = plt.subplots(num="Live Gain Test", figsize=(7, 3.5))
            while self.is_testing:
                try: sdr.gain = float(self.gain.get())
                except: pass
                samples = sdr.read_samples(32768)
                ax.clear(); ax.hist(np.real(samples), bins=64, color='blue', alpha=0.5); ax.set_xlim([-1, 1]); plt.pause(0.1)
                if not plt.fignum_exists("Live Gain Test"): break
            sdr.close(); plt.ioff()
        except Exception as e: messagebox.showerror("Error", str(e))
        finally: self.is_testing = False; self.test_btn.config(text="Gain Test", bg="orange")

    def browse_folder(self):
        f = filedialog.askdirectory()
        if f: self.save_path.set(f)

    def browse_baseline(self):
        f = filedialog.askopenfilename(filetypes=[("FITS files", "*.fits")])
        if f: self.baseline_fits_path.set(f)

    def reset_baseline(self):
        self.baseline_fits_path.set("Not Selected")

    def run_observation(self):
        try:
            sr, cf = self.evaluate_expr(self.sample_rate.get()), self.evaluate_expr(self.center_freq.get())
            gn, nfft = float(self.gain.get()), int(self.evaluate_expr(self.nfft.get()))
            iters, sps = int(self.evaluate_expr(self.iterations.get())), int(self.evaluate_expr(self.samples_per_scan.get()))

            self.run_btn.config(state="disabled", text="OBSERVING...")
            self.root.update()

            obs_sdr = RtlSdr()
            obs_sdr.sample_rate, obs_sdr.center_freq, obs_sdr.gain = sr, cf, gn
            if self.use_bias_tee.get(): obs_sdr.set_bias_tee(True)

            freq_axis = np.fft.fftshift(np.fft.fftfreq(nfft, d=1/sr)) / 1e6 + (cf / 1e6)
            accumulated_psd = np.zeros(nfft)
            window = np.hanning(nfft) if self.use_hanning.get() else np.ones(nfft)

            try:
                for _ in range(iters):
                    samples = obs_sdr.read_samples(sps)
                    if self.remove_dc.get(): samples = samples - np.mean(samples)
                    segments = samples[:(len(samples)//nfft)*nfft].reshape((-1, nfft))
                    fft_res = np.fft.fft(segments * window, axis=1)
                    accumulated_psd += np.mean(np.abs(np.fft.fftshift(fft_res, axes=1))**2, axis=0)
            finally: obs_sdr.close()

            raw_psd_db = 10 * np.log10(accumulated_psd / iters + 1e-12)
            now = datetime.now().strftime('%Y%m%d_%H%M%S')
            folder = os.path.join(self.save_path.get(), f"HI_Obs_{now}")
            os.makedirs(folder, exist_ok=True)

            # --- FITS 저장 ---
            combined_data = np.vstack((freq_axis, raw_psd_db))
            hdu = fits.PrimaryHDU(combined_data)
            hdr = hdu.header
            hdr['DATE-OBS'] = datetime.now().isoformat()
            hdr['FREQ-CEN'] = cf; hdr['SAMPRATE'] = sr; hdr['GAIN'] = gn; hdr['NFFT'] = nfft
            fits_file = os.path.join(folder, f"raw_observation.fits")
            hdu.writeto(fits_file, overwrite=True)

            # --- 그래프 1 (Raw) 시각화 및 저장 ---
            plt.figure("Raw Observation", figsize=(8, 4.5))
            plt.plot(freq_axis, raw_psd_db, 'k', lw=0.7)
            plt.title(f"Raw PSD ({now})")
            plt.xlabel("Frequency (MHz)")
            plt.ylabel("Power (dB)")
            plt.grid(True)
            # 이미지 파일 저장 추가
            raw_img_path = os.path.join(folder, "raw_plot.png")
            plt.savefig(raw_img_path, dpi=300, bbox_inches='tight')
            plt.draw()

            # --- 그래프 2 (Calibrated) 시각화 및 저장 ---
            if self.remove_baseline.get() and os.path.exists(self.baseline_fits_path.get()):
                try:
                    with fits.open(self.baseline_fits_path.get()) as hdul:
                        base_data = hdul[0].data
                        base_power = base_data[1] if base_data.ndim > 1 else base_data
                        
                        if len(base_power) == nfft:
                            cal_psd_db = raw_psd_db - base_power
                            plt.figure("Calibrated Observation", figsize=(8, 4.5))
                            plt.plot(freq_axis, cal_psd_db, 'b', lw=1)
                            plt.axvline(1420.405, color='r', ls='--', label='HI Line (1420.405 MHz)')
                            plt.title(f"Calibrated Spectrum ({now})")
                            plt.xlabel("Frequency (MHz)")
                            plt.ylabel("Relative Power (dB)")
                            plt.grid(True)
                            plt.legend()
                            # 이미지 파일 저장 추가
                            cal_img_path = os.path.join(folder, "calibrated_plot.png")
                            plt.savefig(cal_img_path, dpi=300, bbox_inches='tight')
                        else:
                            messagebox.showwarning("불일치", f"NFFT 크기가 다릅니다.\n파일: {len(base_power)}, 현재: {nfft}")
                except Exception as e:
                    messagebox.showerror("FITS 에러", f"베이스라인 파일을 읽을 수 없습니다: {e}")

            plt.show()
            messagebox.showinfo("완료", f"성공적으로 관측되었습니다.\n저장 위치: {folder}")

        except Exception as e: messagebox.showerror("Error", str(e))
        finally: self.run_btn.config(state="normal", text="START OBSERVATION")

if __name__ == "__main__":
    root = tk.Tk(); app = HIScopeGUI(root); root.mainloop()