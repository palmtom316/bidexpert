/* validation.js — Client-side input validation helpers (R14) */

const Validation = {
  rules: {
    required(value, fieldName) {
      if (!value || !String(value).trim()) {
        return `${fieldName}不能为空`;
      }
      return null;
    },
    uuid(value, fieldName) {
      if (value && !isValidUuid(value)) {
        return `${fieldName}格式不正确，需要有效的UUID`;
      }
      return null;
    },
    minLength(min) {
      return (value, fieldName) => {
        if (value && String(value).trim().length < min) {
          return `${fieldName}至少需要${min}个字符`;
        }
        return null;
      };
    },
    maxLength(max) {
      return (value, fieldName) => {
        if (value && String(value).trim().length > max) {
          return `${fieldName}不能超过${max}个字符`;
        }
        return null;
      };
    },
    fileRequired(fileInput, fieldName) {
      if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
        return `请选择${fieldName}`;
      }
      return null;
    },
  },

  validate(fields) {
    const errors = [];
    for (const { value, name, validators } of fields) {
      for (const validator of validators) {
        const error = typeof validator === "function"
          ? validator(value, name)
          : null;
        if (error) {
          errors.push({ field: name, message: error });
          break;
        }
      }
    }
    return errors;
  },

  showFieldErrors(errors) {
    for (const { field, message } of errors) {
      Toast.warn(`${field}: ${message}`);
    }
  },
};
