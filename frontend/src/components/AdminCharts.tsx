/**
 * Grafik ringan untuk dashboard superadmin.
 *
 * Sengaja tanpa library chart pihak ketiga: cukup `react-native-svg` (sudah
 * dipakai di layar pohon) untuk garis tren, dan View biasa untuk batang.
 * Semua komponen aman dirender di Android/iOS/web.
 */
import { useState } from "react";
import { StyleSheet, Text, View, type LayoutChangeEvent } from "react-native";
import Svg, { Defs, LinearGradient, Path, Stop } from "react-native-svg";

type SparklineProps = {
  values: number[];
  color: string;
  height?: number;
  /** Warna area di bawah garis (biasanya versi transparan dari `color`). */
  fillColor?: string;
  emptyLabel?: string;
};

/** Garis tren dengan area gradasi. Lebar mengikuti kontainer (diukur onLayout). */
export function Sparkline({ values, color, height = 72, fillColor, emptyLabel }: SparklineProps) {
  const [width, setWidth] = useState(0);
  const onLayout = (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width);

  const data = values.length ? values : [0];
  const max = Math.max(...data, 0);
  const min = Math.min(...data, 0);
  const span = max - min || 1;
  const pad = 4;
  const usable = Math.max(1, height - pad * 2);
  const stepX = data.length > 1 ? width / (data.length - 1) : width;

  const point = (i: number, v: number): [number, number] => [
    data.length > 1 ? i * stepX : width / 2,
    height - pad - ((v - min) / span) * usable,
  ];

  const pts = data.map((v, i) => point(i, v));
  const line = pts
    .map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`)
    .join(" ");
  const area =
    width > 0 && pts.length
      ? `${line} L${pts[pts.length - 1][0].toFixed(2)},${height} L${pts[0][0].toFixed(2)},${height} Z`
      : "";

  const flat = max === 0;

  return (
    <View style={{ height }} onLayout={onLayout}>
      {width > 0 ? (
        <Svg width={width} height={height}>
          <Defs>
            <LinearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={fillColor ?? color} stopOpacity={0.22} />
              <Stop offset="1" stopColor={fillColor ?? color} stopOpacity={0.02} />
            </LinearGradient>
          </Defs>
          {area ? <Path d={area} fill="url(#sparkFill)" /> : null}
          {!flat ? (
            <Path d={line} stroke={color} strokeWidth={2} fill="none" strokeLinecap="round" />
          ) : null}
        </Svg>
      ) : null}
      {flat && emptyLabel ? (
        <View style={styles.sparkEmpty}>
          <Text style={styles.sparkEmptyText}>{emptyLabel}</Text>
        </View>
      ) : null}
    </View>
  );
}

type BarsProps = {
  values: number[];
  color: string;
  height?: number;
  /** Ambang minimum tinggi batang (px) supaya nilai 1 tetap terlihat. */
  minBarHeight?: number;
};

/** Diagram batang vertikal sederhana, minggu/hari. */
export function Bars({ values, color, height = 64, minBarHeight = 3 }: BarsProps) {
  const max = Math.max(...values, 1);
  return (
    <View style={[styles.bars, { height }]}>
      {values.map((v, i) => {
        const h = v <= 0 ? 0 : Math.max(minBarHeight, (v / max) * height);
        return (
          <View key={i} style={styles.barSlot}>
            <View style={{ height: h, backgroundColor: color, width: "100%", borderRadius: 3 }} />
          </View>
        );
      })}
    </View>
  );
}

type BarRowProps = {
  label: string;
  value: number;
  max: number;
  color: string;
  caption?: string;
};

/** Satu baris bar horizontal dengan label + nilai. */
export function BarRow({ label, value, max, color, caption }: BarRowProps) {
  const ratio = max > 0 ? Math.min(1, value / max) : 0;
  return (
    <View style={styles.barRow}>
      <View style={styles.barRowHead}>
        <Text style={styles.barRowLabel} numberOfLines={1}>
          {label}
        </Text>
        <Text style={styles.barRowValue}>{caption ?? value.toLocaleString("id-ID")}</Text>
      </View>
      <View style={styles.track}>
        <View
          style={[styles.trackFill, { width: `${Math.max(ratio * 100, value > 0 ? 2 : 0)}%`, backgroundColor: color }]}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  sparkEmpty: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: "center",
    justifyContent: "center",
  },
  sparkEmptyText: { fontSize: 11, color: "#8A8577" },
  bars: { flexDirection: "row", alignItems: "flex-end", gap: 2 },
  barSlot: { flex: 1, justifyContent: "flex-end" },
  barRow: { marginBottom: 10 },
  barRowHead: { flexDirection: "row", justifyContent: "space-between", marginBottom: 4, gap: 8 },
  barRowLabel: { flex: 1, fontSize: 12, color: "#3A3F52" },
  barRowValue: { fontSize: 12, fontWeight: "700", color: "#1F2A44" },
  track: { height: 6, borderRadius: 3, backgroundColor: "#F0EADA", overflow: "hidden" },
  trackFill: { height: 6, borderRadius: 3 },
});
