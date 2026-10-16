package de.linktresor;

import android.media.MediaCodec;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.media.MediaMuxer;

import java.io.File;
import java.nio.ByteBuffer;

/** Fügt Video- und Tonspur ohne Umwandeln zu einer MP4/M4A zusammen (Androids MediaMuxer statt FFmpeg). */
public class Muxer {
    /** inputs: Dateien, aus denen jeweils die erste Spur übernommen wird (z. B. Video + Ton). */
    public static void merge(File out, File... inputs) throws Exception {
        MediaMuxer mux = new MediaMuxer(out.getPath(), MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
        MediaExtractor[] ex = new MediaExtractor[inputs.length];
        int[] track = new int[inputs.length];
        int maxSize = 1024 * 1024;
        try {
            for (int i = 0; i < inputs.length; i++) {
                ex[i] = new MediaExtractor();
                ex[i].setDataSource(inputs[i].getPath());
                if (ex[i].getTrackCount() < 1) throw new Exception("Datei ohne Spur");
                ex[i].selectTrack(0);
                MediaFormat f = ex[i].getTrackFormat(0);
                if (f.containsKey(MediaFormat.KEY_MAX_INPUT_SIZE))
                    maxSize = Math.max(maxSize, f.getInteger(MediaFormat.KEY_MAX_INPUT_SIZE));
                track[i] = mux.addTrack(f);
            }
            mux.start();
            ByteBuffer buf = ByteBuffer.allocate(maxSize * 2);
            MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
            boolean[] done = new boolean[inputs.length];
            while (true) {
                // Spuren abwechselnd nach Zeit schreiben (sauber verzahnt)
                int i = -1;
                for (int k = 0; k < inputs.length; k++)
                    if (!done[k] && (i < 0 || ex[k].getSampleTime() < ex[i].getSampleTime())) i = k;
                if (i < 0) break;
                buf.clear();
                int n = ex[i].readSampleData(buf, 0);
                if (n < 0) {
                    done[i] = true;
                    continue;
                }
                info.offset = 0;
                info.size = n;
                info.presentationTimeUs = ex[i].getSampleTime();
                info.flags = (ex[i].getSampleFlags() & MediaExtractor.SAMPLE_FLAG_SYNC) != 0
                        ? MediaCodec.BUFFER_FLAG_KEY_FRAME : 0;
                mux.writeSampleData(track[i], buf, info);
                ex[i].advance();
            }
            mux.stop();
        } finally {
            for (MediaExtractor e : ex) if (e != null) e.release();
            try {
                mux.release();
            } catch (Exception ignored) {
            }
        }
    }
}
