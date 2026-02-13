"""
codec for Modbus TCP device model handling power and battery parameters.

"""
class DeviceModel:
    HR0_ADDRESS = 0  # demand_control_power R/W
    HR1_ADDRESS = 1  # active_power R

    POWER_SCALE = 0.1  # 0.1 kW / LSB
    # two's complement conversion
    @staticmethod #helper functions for int16 <-> uint16 conversion
    def _int16_to_u16(x: int) -> int:
        return x & 0xFFFF    # fit

    @staticmethod
    def _u16_to_int16(x: int) -> int:
        return x - 0x10000 if x >= 0x8000 else x

    @classmethod
    def encode_power_kw(cls, kw: float) -> int: 
        raw = int(round(kw / cls.POWER_SCALE))  # kW -> 0.1kW units
        if raw < -32768 or raw > 32767:
            raise ValueError("Power out of int16 range after scaling")
        return cls._int16_to_u16(raw)

    @classmethod
    def decode_power_kw(cls, reg_u16: int) -> float: #input is uint16 from register, output is float in kW
        raw = cls._u16_to_int16(reg_u16 & 0xFFFF) # just to be safe, mask to 16 bits before conversion
        return raw * cls.POWER_SCALE #convert back to kW
    
    # 
    @classmethod
    def decode_power_raw_units(cls, reg_u16: int) -> int:
        # u16 (0..65535) -> int16 (-32768..32767)
        return cls._u16_to_int16(reg_u16 & 0xFFFF)
 
    #
    @classmethod
    def encode_power_raw_units(cls, raw: int) -> int:
        if raw < -32768 or raw > 32767:
            raise ValueError("Power raw units out of int16 range")
        return cls._int16_to_u16(raw)

    # --- Unsigned scaled uint16 helpers (SOC, SOH, capacity) ---

    @staticmethod
    def encode_scaled_uint16(value: float, scale: float,
                             min_val: float = 0.0, max_val: float = 6553.5) -> int:
        """Encode float to unsigned uint16 with scale and clamp."""
        clamped = max(min_val, min(max_val, value))
        raw = int(round(clamped / scale))
        return raw & 0xFFFF

    @staticmethod
    def decode_scaled_uint16(reg_u16: int, scale: float) -> float:
        """Decode unsigned uint16 register to float."""
        return (reg_u16 & 0xFFFF) * scale

    @classmethod
    def encode_soc(cls, percent: float) -> int:
        """SOC (0-100%) -> uint16, scale=1."""
        return cls.encode_scaled_uint16(percent, scale=1.0, min_val=0.0, max_val=100.0)

    @classmethod
    def decode_soc(cls, reg_u16: int) -> float:
        """uint16 -> SOC (%)."""
        return cls.decode_scaled_uint16(reg_u16, scale=1.0)

    @classmethod
    def encode_soh(cls, percent: float) -> int:
        """SOH (0-100%) -> uint16, scale=1."""
        return cls.encode_scaled_uint16(percent, scale=1.0, min_val=0.0, max_val=100.0)

    @classmethod
    def decode_soh(cls, reg_u16: int) -> float:
        """uint16 -> SOH (%)."""
        return cls.decode_scaled_uint16(reg_u16, scale=1.0)

    @classmethod
    def encode_capacity_kwh(cls, kwh: float) -> int:
        """Capacity (kWh) -> uint16, scale=0.1, clamp >= 0."""
        return cls.encode_scaled_uint16(kwh, scale=0.1, min_val=0.0, max_val=6553.5)

    @classmethod
    def decode_capacity_kwh(cls, reg_u16: int) -> float:
        """uint16 -> capacity (kWh)."""
        return cls.decode_scaled_uint16(reg_u16, scale=0.1)