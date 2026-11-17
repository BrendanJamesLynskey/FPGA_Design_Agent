/* Short names over the generated register headers (made by hwsw.regmap from the YAML maps in regmaps). */
#ifndef GEN_REGS_H
#define GEN_REGS_H
#include "../gen/regs/zb_accel_regs.h"
#include "../gen/regs/zb_lat_regs.h"
#define ACC_CTRL        ZB_ACCEL_CTRL_OFFSET
#define ACC_CMD         ZB_ACCEL_CMD_OFFSET
#define ACC_STATUS      ZB_ACCEL_STATUS_OFFSET
#define ACC_JOB_CYCLES  ZB_ACCEL_JOB_CYCLES_OFFSET
#define ACC_IN_BEATS    ZB_ACCEL_IN_BEATS_OFFSET
#define ACC_OUT_BEATS   ZB_ACCEL_OUT_BEATS_OFFSET
#define ACC_COEF(i)     (ZB_ACCEL_COEF0_OFFSET + 4u * (i))
#define LAT_CMD         ZB_LAT_CMD_OFFSET
#define LAT_DELAY       ZB_LAT_DELAY_OFFSET
#define LAT_NOW         ZB_LAT_NOW_OFFSET
#define LAT_T_FIRE      ZB_LAT_T_FIRE_OFFSET
#define LAT_T_ACK       ZB_LAT_T_ACK_OFFSET
#define LAT_IRQ_STATUS  ZB_LAT_IRQ_STATUS_OFFSET
#define LAT_IRQ_ENABLE  ZB_LAT_IRQ_ENABLE_OFFSET
#define LAT_BASE        (PL_BASE + 0x00000u)
#define HOLE_BASE(i)    (PL_BASE + 0x10000u * (1u + (i)))      /* 0 okay, 1 slverr, 2 split */
#endif
