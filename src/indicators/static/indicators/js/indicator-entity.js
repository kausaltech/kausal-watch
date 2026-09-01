function registerIndicatorEntity() {
  class IndicatorChooserModalOnloadHandlerFactory extends window.ChooserModalOnloadHandlerFactory {
    ajaxifyLinks(modal, context) {
      super.ajaxifyLinks(modal, context);
    }
  }

  window.INDICATOR_CHOOSER_MODAL_ONLOAD_HANDLERS =
    new IndicatorChooserModalOnloadHandlerFactory({
      searchInputDelay: 50,
    }).getOnLoadHandlers();

  class IndicatorChooserModal extends window.DocumentChooserModal {
    onloadHandlers = window.INDICATOR_CHOOSER_MODAL_ONLOAD_HANDLERS;
  }
  window.IndicatorChooserModal = IndicatorChooserModal;

  class IndicatorModalWorkflowSource extends draftail.ModalWorkflowSource {
    getChooserConfig() {
      const { indicatorChooser } = {
        ...this.props.entityType?.chooserUrls,
      };

      return {
        url: indicatorChooser,
        urlParams: {},
        onload: window.INDICATOR_CHOOSER_MODAL_ONLOAD_HANDLERS,
        responses: {
          chosen: this.onChosen,
        },
      };
    }

    filterEntityData(data) {
      console.log("indicator filterEntityData", data);
      return {
        edit_url: data.edit_url,
        id: data.id,
        title: data.title,
        uuid: data.uuid,
      };
    }
  }

  const IndicatorLink = (props) => {
    const { entityKey, contentState } = props;
    const data = contentState.getEntity(entityKey).getData();

    const TooltipEntity = draftail.TooltipEntity;
    return React.createElement(TooltipEntity, {
      icon: "#icon-kausal-indicator",
      label: data.title,
      url: data.edit_url,
      ...props,
    });
  };

  draftail.registerPlugin({
    type: "INDICATOR",
    source: IndicatorModalWorkflowSource,
    decorator: IndicatorLink,
  });
}

registerIndicatorEntity();
